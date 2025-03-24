# core/utils/rss_feed_manager.py

import logging
import threading
import time
import re
import os
import tempfile
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from core.knowledge_base.models import RSSFeed, RSSFeedEntry, Document, Category, rss_feed_document_association
from core.utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class RSSFeedManager:
    """Manages RSS feeds, including updating, importing, and processing."""
    
    def __init__(self, db_session: Session, settings_manager: Optional[SettingsManager] = None):
        """
        Initialize the RSS feed manager.
        
        Args:
            db_session: SQLAlchemy database session
            settings_manager: Optional settings manager instance
        """
        self.db_session = db_session
        self.settings_manager = settings_manager or SettingsManager()
        self.running = False
        self.update_thread = None
        self._user_agent = "Incrementum RSS Reader"
    
    def start_feed_update_timer(self):
        """Start the background thread for updating feeds."""
        if self.update_thread is not None and self.update_thread.is_alive():
            logger.warning("Feed update thread already running")
            return
            
        self.running = True
        self.update_thread = threading.Thread(
            target=self._update_feeds_thread,
            daemon=True,
            name="RSS-Feed-Updater"
        )
        self.update_thread.start()
        logger.info("Started RSS feed update thread")
    
    def stop_feed_update_timer(self):
        """Stop the background thread for updating feeds."""
        self.running = False
        if self.update_thread:
            # Wait for thread to finish, with timeout
            self.update_thread.join(2.0)
            if self.update_thread.is_alive():
                logger.warning("Feed update thread didn't exit cleanly")
            else:
                logger.info("Stopped RSS feed update thread")
        self.update_thread = None
        
    def _update_feeds_thread(self):
        """Background thread to periodically update RSS feeds."""
        # Wait a short time before first check to allow application to fully load
        time.sleep(5)
        
        while self.running:
            try:
                # Check which feeds need updating
                due_feeds = self.get_feeds_due_for_update()
                
                if due_feeds:
                    logger.info(f"Updating {len(due_feeds)} RSS feeds...")
                    for feed in due_feeds:
                        try:
                            new_entries = self.update_feed(feed)
                            logger.info(f"Updated feed '{feed.title}': {len(new_entries)} new entries")
                            
                            # Import new entries if auto-import is enabled
                            if feed.auto_import:
                                self.import_new_entries(feed)
                                
                        except Exception as e:
                            logger.error(f"Error updating feed '{feed.title}': {str(e)}")
            
            except Exception as e:
                logger.exception(f"Error in RSS feed update thread: {str(e)}")
            
            # Sleep for the check interval
            check_interval = self.settings_manager.get_setting("rss", "check_interval_minutes", 15)
            time.sleep(check_interval * 60)
    
    def get_feeds_due_for_update(self) -> List[RSSFeed]:
        """
        Get a list of RSS feeds that are due for update.
        
        Returns:
            List of RSS feed objects due for update
        """
        now = datetime.utcnow()
        due_feeds = []
        
        feeds = self.db_session.query(RSSFeed).filter(
            RSSFeed.enabled == True
        ).all()
        
        for feed in feeds:
            # If feed has never been checked or is due based on frequency
            if feed.last_checked is None or \
                feed.last_checked + timedelta(minutes=feed.check_frequency) <= now:
                due_feeds.append(feed)
        
        return due_feeds
    
    def update_feed(self, feed: RSSFeed) -> List[RSSFeedEntry]:
        """
        Update a feed with new entries.
        
        Args:
            feed: The RSSFeed to update
            
        Returns:
            List of new RSSFeedEntry objects created
        """
        logger.info(f"Updating feed: {feed.title}")
        
        # Parse feed
        parsed_feed = feedparser.parse(feed.url)
        
        if not parsed_feed or not hasattr(parsed_feed, 'entries'):
            logger.error(f"Error parsing feed: {feed.url}")
            return []
        
        # Get existing entries for this feed
        existing_entries = self.db_session.query(RSSFeedEntry).filter(
            RSSFeedEntry.feed_id == feed.id
        ).all()
        
        existing_entry_ids = {
            entry.entry_id: entry for entry in existing_entries
        }
        
        # Process new entries
        new_entries = []
        
        for entry in parsed_feed.entries:
            # Use guid or link as unique identifier
            entry_id = getattr(entry, 'id', None) or entry.link
            
            if entry_id in existing_entry_ids:
                continue  # Skip existing entries
            
            # Create new entry
            published = getattr(entry, 'published_parsed', None)
            if published:
                publish_date = datetime(*published[:6])
            else:
                publish_date = datetime.utcnow()
            
            # Get the actual link - this is important for downloading content later
            entry_link = getattr(entry, 'link', None)
            
            new_entry = RSSFeedEntry(
                feed_id=feed.id,
                entry_id=entry_id,
                title=getattr(entry, 'title', 'Untitled'),
                publish_date=publish_date,
                processed=False,
                link_url=entry_link  # Store the URL for downloading content later
            )
            
            self.db_session.add(new_entry)
            new_entries.append(new_entry)
        
        # Update feed information
        feed.title = getattr(parsed_feed.feed, 'title', feed.title)
        feed.last_checked = datetime.utcnow()
        
        # Commit changes
        self.db_session.commit()
        
        return new_entries
    
    def import_new_entries(self, feed: RSSFeed) -> List[Document]:
        """
        Import new unprocessed entries for a feed as documents.
        
        Args:
            feed: The RSSFeed to import entries from
            
        Returns:
            List of Document objects created
        """
        # Get unprocessed entries
        unprocessed_entries = self.db_session.query(RSSFeedEntry).filter(
            RSSFeedEntry.feed_id == feed.id,
            RSSFeedEntry.processed == False
        ).all()
        
        if not unprocessed_entries:
            logger.info(f"No new entries to import for feed '{feed.title}'")
            return []
        
        imported_documents = []
        
        for entry in unprocessed_entries:
            try:
                # Get the entry URL - preferring link_url if available, otherwise try to use entry_id if it's a URL
                entry_link = None
                
                # First check the link_url field
                if entry.link_url and entry.link_url.startswith(('http://', 'https://')):
                    entry_link = entry.link_url
                # Then check if entry_id is a valid URL
                elif entry.entry_id and entry.entry_id.startswith(('http://', 'https://')):
                    entry_link = entry.entry_id
                # Handle ZeroHedge and similar sites that use "ID at domain.com" format
                elif ' at ' in entry.entry_id:
                    # Parse domain from the entry_id
                    parts = entry.entry_id.split(' at ')
                    if len(parts) == 2 and parts[1].startswith(('http://', 'https://', 'www.')):
                        domain = parts[1]
                        if not domain.startswith(('http://', 'https://')):
                            domain = 'https://' + domain
                        
                        # For ZeroHedge specifically, we can construct article URLs from IDs
                        if 'zerohedge.com' in domain.lower():
                            article_id = parts[0].strip()
                            entry_link = f"{domain}/news/id/{article_id}"
                        else:
                            # For other feeds with similar format, try to re-parse
                            try:
                                parsed_feed = feedparser.parse(feed.url)
                                for feed_entry in parsed_feed.entries:
                                    if getattr(feed_entry, 'id', '') == entry.entry_id and hasattr(feed_entry, 'link'):
                                        entry_link = feed_entry.link
                                        # Update entry for future use
                                        entry.link_url = entry_link
                                        break
                            except Exception as e:
                                logger.warning(f"Error parsing feed to get link: {str(e)}")
                else:
                    # If no valid URL found, try to re-parse the feed to get the link for this entry
                    try:
                        parsed_feed = feedparser.parse(feed.url)
                        for feed_entry in parsed_feed.entries:
                            if getattr(feed_entry, 'id', '') == entry.entry_id and hasattr(feed_entry, 'link'):
                                entry_link = feed_entry.link
                                # Update the entry with the link for future use
                                entry.link_url = entry_link
                                break
                    except Exception as e:
                        logger.warning(f"Error re-parsing feed to get link: {str(e)}")
                
                if not entry_link:
                    logger.warning(f"No link found for entry '{entry.title}'")
                    continue
                
                # Download content
                html_content = self._download_article_content(entry_link)
                
                if not html_content:
                    logger.warning(f"Could not download content for '{entry.title}'")
                    continue
                
                # Create temporary file for content
                file_path = self._save_content_to_file(html_content, entry.title)
                
                if not file_path:
                    logger.warning(f"Could not save content for '{entry.title}'")
                    continue
                
                # Create document
                document = Document(
                    title=entry.title,
                    source_url=entry_link,
                    file_path=file_path,
                    content_type="html",
                    category_id=feed.category_id,
                    imported_date=datetime.utcnow(),
                    last_accessed=datetime.utcnow(),
                    priority=self.settings_manager.get_setting("rss", "default_priority", 50)
                )
                
                self.db_session.add(document)
                self.db_session.flush()  # Get ID without committing transaction
                
                # Update entry with document ID
                entry.document_id = document.id
                entry.processed = True
                entry.processed_date = datetime.utcnow()
                
                # Associate document with feed
                feed.documents.append(document)
                
                imported_documents.append(document)
                
            except Exception as e:
                logger.exception(f"Error importing entry '{entry.title}': {str(e)}")
        
        # Commit all changes
        self.db_session.commit()
        
        # Cleanup - remove oldest documents if we exceed max_items_to_keep
        if feed.max_items_to_keep > 0:
            self._cleanup_old_documents(feed)
        
        return imported_documents
    
    def _download_article_content(self, url: str) -> Optional[str]:
        """
        Download and extract the article content from a URL.
        
        Args:
            url: The URL to download
            
        Returns:
            HTML content as string, or None if download failed
        """
        try:
            response = requests.get(url, headers={'User-Agent': self._user_agent}, timeout=10)
            response.raise_for_status()
            
            html_content = response.text
            
            # Try to extract just the article content for better readability
            try:
                from bs4 import BeautifulSoup
                import html2text
                
                # Parse the HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Remove unwanted elements that are typically not part of the main content
                for element in soup.select('script, style, nav, footer, header, aside, .ads, .advertisement, .sidebar, .comments, .social-media, .sharing, .related-posts'):
                    element.decompose()
                
                # Try to find the main article content
                article_content = None
                
                # Common article containers
                article_selectors = [
                    'article', 
                    '.post-content', 
                    '.article-content',
                    '.entry-content', 
                    '.content-area', 
                    '.main-content',
                    '#content', 
                    '.post', 
                    'main',
                    '[itemprop="articleBody"]'
                ]
                
                # Look for article content
                for selector in article_selectors:
                    content = soup.select_one(selector)
                    if content and len(content.get_text(strip=True)) > 100:
                        article_content = content
                        break
                
                # If we found article content, use that instead of the full page
                if article_content:
                    # Create a new soup with just the article
                    new_soup = BeautifulSoup('<html><head></head><body></body></html>', 'html.parser')
                    
                    # Copy the title
                    if soup.title:
                        new_title = new_soup.new_tag('title')
                        new_title.string = soup.title.string
                        new_soup.head.append(new_title)
                    
                    # Copy any meta tags
                    for meta in soup.find_all('meta'):
                        new_soup.head.append(meta)
                    
                    # Extract stylesheets
                    for link in soup.find_all('link', rel='stylesheet'):
                        new_soup.head.append(link)
                    
                    # Add article content
                    article_wrapper = new_soup.new_tag('article')
                    article_wrapper.append(article_content)
                    new_soup.body.append(article_wrapper)
                    
                    # Get the processed content
                    html_content = str(new_soup)
                    logger.info(f"Successfully extracted article content from {url}")
                else:
                    logger.warning(f"Could not find article content in {url}, using full page")
                
            except Exception as e:
                logger.warning(f"Error extracting article content: {e}. Using full page content.")
            
            return html_content
            
        except Exception as e:
            logger.error(f"Error downloading content from {url}: {str(e)}")
            return None
    
    def _save_content_to_file(self, content: str, title: str) -> Optional[str]:
        """
        Save content to a file in the data directory.
        
        Args:
            content: The HTML content to save
            title: The title for the file
            
        Returns:
            Path to the saved file, or None if save failed
        """
        try:
            # Create safe filename from title
            safe_title = re.sub(r'[^\w\-_]', '_', title)
            safe_title = safe_title[:50]  # Limit length
            
            # Get data directory from settings
            from appdirs import user_data_dir
            data_dir = user_data_dir("Incrementum", "Incrementum")
            rss_dir = os.path.join(data_dir, "rss_content")
            os.makedirs(rss_dir, exist_ok=True)
            
            # Create unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_title}_{timestamp}.html"
            file_path = os.path.join(rss_dir, filename)
            
            # Process HTML content to ensure it's valid and displayable
            try:
                from bs4 import BeautifulSoup
                
                # Clean the HTML with BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')
                
                # Check if we have proper HTML structure
                if not soup.html:
                    # Create proper HTML structure
                    new_soup = BeautifulSoup('<html><head></head><body></body></html>', 'html.parser')
                    
                    # Add title if we don't have one
                    if not soup.title and title:
                        new_title = new_soup.new_tag('title')
                        new_title.string = title
                        new_soup.head.append(new_title)
                    
                    # Move all content to body
                    new_soup.body.extend(soup.contents)
                    soup = new_soup
                
                # Add meta charset if missing
                if not soup.find('meta', charset=True):
                    meta = soup.new_tag('meta')
                    meta['charset'] = 'utf-8'
                    if soup.head:
                        soup.head.insert(0, meta)
                
                # Add responsive viewport if missing
                if not soup.find('meta', attrs={'name': 'viewport'}):
                    viewport = soup.new_tag('meta')
                    viewport['name'] = 'viewport'
                    viewport['content'] = 'width=device-width, initial-scale=1'
                    if soup.head:
                        soup.head.append(viewport)
                
                # Add basic styling for readability
                if not soup.find('style'):
                    style = soup.new_tag('style')
                    style.string = """
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                        line-height: 1.6;
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 1rem;
                        color: #333;
                    }
                    img { max-width: 100%; height: auto; }
                    pre, code { background: #f5f5f5; padding: 0.2em; border-radius: 3px; }
                    blockquote { border-left: 4px solid #ddd; padding-left: 1em; margin-left: 0; color: #666; }
                    a { color: #0066cc; }
                    h1, h2, h3, h4, h5, h6 { line-height: 1.3; }
                    """
                    if soup.head:
                        soup.head.append(style)
                
                # Get the processed content
                content = str(soup)
                
                # Log the content length
                logger.debug(f"Processed HTML content length: {len(content)} bytes")
                
            except Exception as e:
                logger.warning(f"Error processing HTML content: {e}. Using original content.")
            
            # Write content to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"Saved RSS content to {file_path} ({os.path.getsize(file_path)} bytes)")
            return file_path
            
        except Exception as e:
            logger.error(f"Error saving content for '{title}': {str(e)}")
            return None
    
    def _cleanup_old_documents(self, feed: RSSFeed):
        """
        Remove oldest documents associated with a feed if we exceed max_items_to_keep.
        
        Args:
            feed: The RSS feed to clean up
        """
        try:
            # Count documents for this feed
            document_count = len(feed.documents)
            
            if document_count <= feed.max_items_to_keep:
                return  # No cleanup needed
            
            # Get excess documents to remove, ordered by imported date
            excess_count = document_count - feed.max_items_to_keep
            
            document_ids = [
                doc_id for doc_id, in self.db_session.query(Document.id)
                .join(rss_feed_document_association, Document.id == rss_feed_document_association.c.document_id)
                .filter(rss_feed_document_association.c.rss_feed_id == feed.id)
                .order_by(Document.imported_date.asc())
                .limit(excess_count)
            ]
            
            # Delete documents
            for doc_id in document_ids:
                document = self.db_session.query(Document).get(doc_id)
                if document:
                    # Delete associated file if it exists
                    if document.file_path and os.path.exists(document.file_path):
                        try:
                            os.remove(document.file_path)
                        except OSError as e:
                            logger.warning(f"Could not delete file for document {doc_id}: {str(e)}")
                    
                    # Delete document from database
                    self.db_session.delete(document)
            
            self.db_session.commit()
            logger.info(f"Cleaned up {len(document_ids)} old documents for feed '{feed.title}'")
            
        except Exception as e:
            logger.exception(f"Error cleaning up documents for feed '{feed.title}': {str(e)}")
    
    def add_feed(self, url: str, title: Optional[str] = None, category_id: Optional[int] = None) -> Optional[RSSFeed]:
        """
        Add a new RSS feed.
        
        Args:
            url: The RSS feed URL
            title: Optional title for the feed (will be fetched from feed if not provided)
            category_id: Optional category ID to assign to the feed
            
        Returns:
            The created RSSFeed, or None if creation failed
        """
        try:
            # Check if URL is already in database
            existing = self.db_session.query(RSSFeed).filter(RSSFeed.url == url).first()
            if existing:
                logger.warning(f"Feed URL already exists: {url}")
                return existing
            
            # Try to parse the feed to verify it and get title if needed
            parsed = feedparser.parse(url)
            
            if not parsed or not hasattr(parsed, 'feed') or not hasattr(parsed, 'entries'):
                logger.error(f"Invalid RSS feed: {url}")
                return None
            
            if not title:
                title = getattr(parsed.feed, 'title', url)
            
            # Create new feed
            feed = RSSFeed(
                title=title,
                url=url,
                category_id=category_id,
                check_frequency=self.settings_manager.get_setting("rss", "default_check_frequency", 60),
                auto_import=self.settings_manager.get_setting("rss", "default_auto_import", True),
                max_items_to_keep=self.settings_manager.get_setting("rss", "default_max_items", 50)
            )
            
            self.db_session.add(feed)
            self.db_session.commit()
            
            # Fetch initial entries
            self.update_feed(feed)
            
            return feed
            
        except Exception as e:
            logger.exception(f"Error adding feed: {str(e)}")
            self.db_session.rollback()
            return None
    
    def delete_feed(self, feed_id: int, delete_documents: bool = False) -> bool:
        """
        Delete an RSS feed.
        
        Args:
            feed_id: The ID of the feed to delete
            delete_documents: Whether to also delete documents imported from this feed
            
        Returns:
            True if deletion was successful
        """
        try:
            feed = self.db_session.query(RSSFeed).get(feed_id)
            if not feed:
                logger.warning(f"Feed with ID {feed_id} not found")
                return False
            
            if delete_documents:
                # Get documents associated with this feed
                document_ids = [
                    doc_id for doc_id, in self.db_session.query(Document.id)
                    .join(rss_feed_document_association, Document.id == rss_feed_document_association.c.document_id)
                    .filter(rss_feed_document_association.c.rss_feed_id == feed_id)
                ]
                
                # Delete documents
                for doc_id in document_ids:
                    document = self.db_session.query(Document).get(doc_id)
                    if document:
                        # Delete associated file if it exists
                        if document.file_path and os.path.exists(document.file_path):
                            try:
                                os.remove(document.file_path)
                            except OSError as e:
                                logger.warning(f"Could not delete file for document {doc_id}: {str(e)}")
                        
                        # Delete document from database
                        self.db_session.delete(document)
            
            # Delete feed entries
            self.db_session.query(RSSFeedEntry).filter(RSSFeedEntry.feed_id == feed_id).delete()
            
            # Delete feed
            self.db_session.delete(feed)
            self.db_session.commit()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error deleting feed: {str(e)}")
            self.db_session.rollback()
            return False
            
    def get_all_feeds(self) -> List[RSSFeed]:
        """
        Get all RSS feeds.
        
        Returns:
            List of all RSSFeed objects
        """
        return self.db_session.query(RSSFeed).all()
    
    def update_all_feeds(self) -> Dict[int, List[RSSFeedEntry]]:
        """
        Update all enabled RSS feeds.
        
        Returns:
            Dictionary mapping feed ID to list of new entries
        """
        feeds = self.db_session.query(RSSFeed).filter(RSSFeed.enabled == True).all()
        results = {}
        
        for feed in feeds:
            try:
                new_entries = self.update_feed(feed)
                results[feed.id] = new_entries
            except Exception as e:
                logger.error(f"Error updating feed '{feed.title}': {str(e)}")
                results[feed.id] = []
        
        return results
        
    def import_all_new_entries(self) -> Dict[int, List[Document]]:
        """
        Import all new entries from all feeds with auto_import enabled.
        
        Returns:
            Dictionary mapping feed ID to list of imported documents
        """
        feeds = self.db_session.query(RSSFeed).filter(
            RSSFeed.enabled == True,
            RSSFeed.auto_import == True
        ).all()
        
        results = {}
        
        for feed in feeds:
            try:
                documents = self.import_new_entries(feed)
                results[feed.id] = documents
            except Exception as e:
                logger.error(f"Error importing entries for feed '{feed.title}': {str(e)}")
                results[feed.id] = []
        
        return results 