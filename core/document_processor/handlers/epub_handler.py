# core/document_processor/handlers/epub_handler.py

import os
import logging
import tempfile
import requests
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import uuid

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from .base_handler import DocumentHandler

logger = logging.getLogger(__name__)

class EPUBHandler(DocumentHandler):
    """Handler for processing EPUB documents."""
    
    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Extract metadata from an EPUB document.
        
        Args:
            file_path: Path to the EPUB file
            
        Returns:
            Dictionary of metadata
        """
        metadata = {
            'title': os.path.basename(file_path),
            'author': '',
            'creation_date': None,
            'modification_date': None,
            'language': '',
            'publisher': '',
            'description': '',
            'subjects': [],
            'rights': '',
            'identifier': '',
            'page_count': 0,
            'toc': []
        }
        
        try:
            # Load the ebook
            book = epub.read_epub(file_path)
            
            # Extract basic metadata
            if book.get_metadata('DC', 'title'):
                metadata['title'] = book.get_metadata('DC', 'title')[0][0]
            
            if book.get_metadata('DC', 'creator'):
                # EPUB can have multiple creators
                creators = []
                for creator in book.get_metadata('DC', 'creator'):
                    if isinstance(creator, tuple) and len(creator) > 0:
                        creators.append(creator[0])
                metadata['author'] = ', '.join(creators)
            
            if book.get_metadata('DC', 'date'):
                date_str = book.get_metadata('DC', 'date')[0][0]
                try:
                    # Try to parse various date formats
                    for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m', '%Y']:
                        try:
                            metadata['creation_date'] = datetime.strptime(date_str[:10], fmt)
                            break
                        except ValueError:
                            continue
                except Exception:
                    logger.warning(f"Could not parse EPUB date: {date_str}")
            
            if book.get_metadata('DC', 'language'):
                metadata['language'] = book.get_metadata('DC', 'language')[0][0]
            
            if book.get_metadata('DC', 'publisher'):
                metadata['publisher'] = book.get_metadata('DC', 'publisher')[0][0]
            
            if book.get_metadata('DC', 'description'):
                metadata['description'] = book.get_metadata('DC', 'description')[0][0]
            
            if book.get_metadata('DC', 'subject'):
                metadata['subjects'] = [s[0] for s in book.get_metadata('DC', 'subject')]
            
            if book.get_metadata('DC', 'rights'):
                metadata['rights'] = book.get_metadata('DC', 'rights')[0][0]
            
            if book.get_metadata('DC', 'identifier'):
                metadata['identifier'] = book.get_metadata('DC', 'identifier')[0][0]
            
            # Count the number of content documents (approximate page count)
            metadata['page_count'] = len(list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT)))
            
            # Extract table of contents
            metadata['toc'] = self._extract_toc(book)
            
        except Exception as e:
            logger.exception(f"Error extracting EPUB metadata: {e}")
        
        return metadata
    
    def _extract_toc(self, book) -> List[Dict[str, Any]]:
        """Extract table of contents from EPUB book."""
        toc = []
        
        try:
            # Process TOC from epub
            for toc_item in book.toc:
                if isinstance(toc_item, tuple) and len(toc_item) > 0:
                    # Item with children
                    item = toc_item[0]
                    children = toc_item[1]
                    
                    toc_entry = {
                        'title': item.title,
                        'href': item.href if hasattr(item, 'href') else '',
                        'level': 1,
                        'children': []
                    }
                    
                    # Process children
                    for child in children:
                        if hasattr(child, 'title'):
                            child_entry = {
                                'title': child.title,
                                'href': child.href if hasattr(child, 'href') else '',
                                'level': 2
                            }
                            toc_entry['children'].append(child_entry)
                    
                    toc.append(toc_entry)
                else:
                    # Simple item
                    if hasattr(toc_item, 'title'):
                        toc_entry = {
                            'title': toc_item.title,
                            'href': toc_item.href if hasattr(toc_item, 'href') else '',
                            'level': 1
                        }
                        toc.append(toc_entry)
        except Exception as e:
            logger.warning(f"Error extracting TOC from EPUB: {e}")
        
        return toc
    
    def extract_content(self, file_path: str) -> Dict[str, Any]:
        """
        Extract content from an EPUB document.
        
        Args:
            file_path: Path to the EPUB file
            
        Returns:
            Dictionary containing extracted content and structure
        """
        result = {
            'text': '',
            'html': '',
            'chapters': [],
            'toc': [],
            'images': []
        }
        
        try:
            # Load the ebook
            book = epub.read_epub(file_path)
            
            # Extract TOC
            result['toc'] = self._extract_toc(book)
            
            # Process all HTML documents
            full_text = []
            chapters = []
            
            # Get spine items to maintain reading order
            spine_items = []
            for item_id in book.spine:
                try:
                    # spine contains tuples of (id, linear)
                    if isinstance(item_id, tuple):
                        item_id = item_id[0]
                    
                    item = book.get_item_with_id(item_id)
                    if item:
                        spine_items.append(item)
                except Exception as e:
                    logger.warning(f"Error getting spine item {item_id}: {e}")
            
            # If spine is empty, fall back to all document items
            if not spine_items:
                spine_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
            
            # Process spine items
            for item in spine_items:
                try:
                    # Get content
                    content = item.get_content().decode('utf-8', errors='replace')
                    
                    # Parse with BeautifulSoup
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Extract text
                    text = soup.get_text(' ', strip=True)
                    full_text.append(text)
                    
                    # Add to chapters
                    chapter = {
                        'id': item.id,
                        'href': item.file_name,
                        'title': self._find_title(soup, item) or '',
                        'text': text,
                        'html': content
                    }
                    chapters.append(chapter)
                except Exception as e:
                    logger.warning(f"Error processing EPUB document {item.id}: {e}")
            
            # Combine all text
            result['text'] = '\n\n'.join(full_text)
            result['chapters'] = chapters
            
            # Extract image information
            result['images'] = self._extract_images(book)
            
        except Exception as e:
            logger.exception(f"Error extracting EPUB content: {e}")
        
        return result
    
    def _find_title(self, soup, item) -> Optional[str]:
        """Find title for a chapter from the HTML content."""
        # Try to find title in h1 or h2 elements
        for header in soup.find_all(['h1', 'h2']):
            return header.get_text(strip=True)
        
        # If no header found, use the file name as fallback
        if hasattr(item, 'file_name'):
            base_name = os.path.basename(item.file_name)
            # Remove extension and replace underscores/hyphens with spaces
            title = os.path.splitext(base_name)[0].replace('_', ' ').replace('-', ' ')
            return title
        
        return None
    
    def _extract_images(self, book) -> List[Dict[str, Any]]:
        """Extract image information from EPUB book."""
        images = []
        
        try:
            for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                image_info = {
                    'id': item.id,
                    'href': item.file_name,
                    'media_type': item.media_type,
                    'size': len(item.get_content()) if hasattr(item, 'get_content') else 0
                }
                images.append(image_info)
        except Exception as e:
            logger.warning(f"Error extracting images from EPUB: {e}")
        
        return images
    
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download an EPUB document from a URL.
        
        Args:
            url: URL to download from
            
        Returns:
            Tuple of (local file path, metadata)
        """
        metadata = {}
        
        try:
            # Create a unique filename for the download
            temp_filename = f"epub_download_{uuid.uuid4().hex}.epub"
            
            # Create a temporary file
            fd, temp_path = tempfile.mkstemp(suffix='.epub')
            os.close(fd)
            
            # Download the file
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Save content to temp file
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Extract metadata
            metadata = self.extract_metadata(temp_path)
            metadata['source_url'] = url
            
            return temp_path, metadata
            
        except Exception as e:
            logger.exception(f"Error downloading EPUB: {e}")
            return None, metadata
