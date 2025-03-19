# core/document_processor/handlers/epub_handler.py

import os
import logging
import tempfile
import requests
import shutil
import zipfile
import chardet
import html2text
import io
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from .base_handler import DocumentHandler

logger = logging.getLogger(__name__)

class EPUBHandler(DocumentHandler):
    """
    Handler for processing EPUB documents with improved content extraction.
    """
    
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
            'toc': []
        }
        
        try:
            # Suppress warnings from ebooklib
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                book = epub.read_epub(file_path)
            
            # Extract metadata
            if book.get_metadata('DC', 'title'):
                metadata['title'] = book.get_metadata('DC', 'title')[0][0]
            
            if book.get_metadata('DC', 'creator'):
                metadata['author'] = book.get_metadata('DC', 'creator')[0][0]
            
            if book.get_metadata('DC', 'date'):
                date_str = book.get_metadata('DC', 'date')[0][0]
                try:
                    metadata['creation_date'] = datetime.fromisoformat(date_str)
                except ValueError:
                    pass
            
            if book.get_metadata('DC', 'language'):
                metadata['language'] = book.get_metadata('DC', 'language')[0][0]
            
            if book.get_metadata('DC', 'publisher'):
                metadata['publisher'] = book.get_metadata('DC', 'publisher')[0][0]
            
            # Extract table of contents
            toc = book.toc
            for item in toc:
                if isinstance(item, tuple):
                    metadata['toc'].append({
                        'title': item[0].title,
                        'href': item[0].href
                    })
                else:
                    metadata['toc'].append({
                        'title': item.title,
                        'href': item.href
                    })
            
        except Exception as e:
            logger.exception(f"Error extracting EPUB metadata: {e}")
        
        return metadata
    
    def extract_content(self, file_path: str) -> Dict[str, Any]:
        """
        Extract content from an EPUB document with enhanced format support.
        
        Args:
            file_path: Path to the EPUB file
            
        Returns:
            Dictionary containing extracted content and structure
        """
        result = {
            'text': '',
            'html': '',
            'markdown': '',
            'chapters': [],
            'toc': []
        }
        
        try:
            # Suppress warnings from ebooklib
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                book = epub.read_epub(file_path)
            
            # Process TOC
            toc = book.toc
            for item in toc:
                if isinstance(item, tuple):
                    result['toc'].append({
                        'title': item[0].title,
                        'href': item[0].href
                    })
                else:
                    result['toc'].append({
                        'title': item.title,
                        'href': item.href
                    })
            
            # Build a combined HTML document with all chapters
            all_html = []
            all_html.append('<!DOCTYPE html>\n<html>\n<head>\n<meta charset="UTF-8">\n')
            
            # Add title
            if book.get_metadata('DC', 'title'):
                title = book.get_metadata('DC', 'title')[0][0]
                all_html.append(f'<title>{title}</title>\n')
            
            # Add CSS from the EPUB
            css_content = ''
            for item in book.get_items_of_type(ebooklib.ITEM_STYLE):
                try:
                    css_text = item.get_content().decode('utf-8', errors='replace')
                    css_content += css_text + '\n'
                except Exception as e:
                    logger.warning(f"Error extracting CSS: {e}")
            
            if css_content:
                all_html.append(f'<style>\n{css_content}\n</style>\n')
            else:
                # Add default style if no CSS was found
                all_html.append("""
                <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; margin: 2em; }
                h1, h2, h3 { color: #333; }
                img { max-width: 100%; height: auto; }
                </style>
                """)
            
            all_html.append('</head>\n<body>\n')
            
            # Map of image IDs to base64 encoded data
            images = {}
            for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
                try:
                    image_id = item.id
                    image_href = item.get_name()
                    images[image_href] = image_id
                except Exception as e:
                    logger.warning(f"Error processing image: {e}")
            
            # Extract content chapter by chapter
            for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                try:
                    # Get raw content
                    content = item.get_content().decode('utf-8', errors='replace')
                    
                    # Fix relative paths for images
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Process images within the chapter
                    for img in soup.find_all('img'):
                        src = img.get('src', '')
                        
                        # Fix relative paths
                        if src in images:
                            # Point to original file path in our setup
                            img['src'] = src
                    
                    # Clean up HTML content
                    clean_html = str(soup)
                    
                    # Extract text
                    text = soup.get_text(separator='\n\n')
                    
                    # Add chapter to combined HTML
                    all_html.append(f'<div class="chapter" id="{item.id}">\n')
                    all_html.append(clean_html)
                    all_html.append('</div>\n')
                    
                    # Add to chapters
                    result['chapters'].append({
                        'id': item.id,
                        'href': item.get_name(),
                        'html': clean_html,
                        'text': text
                    })
                    
                    # Add to full text
                    result['text'] += text + '\n\n'
                    
                except Exception as e:
                    logger.warning(f"Error processing EPUB item {item.id}: {e}")
            
            all_html.append('</body>\n</html>')
            
            # Combined HTML content
            result['html'] = '\n'.join(all_html)
            
            # Generate markdown
            h2t = html2text.HTML2Text()
            h2t.ignore_links = False
            h2t.ignore_images = False
            h2t.unicode_snob = True
            h2t.single_line_break = False
            result['markdown'] = h2t.handle(result['html'])
            
            # Save HTML for easier viewing
            html_path = os.path.splitext(file_path)[0] + '.html'
            try:
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(result['html'])
                logger.info(f"Saved HTML version of EPUB to {html_path}")
            except Exception as e:
                logger.warning(f"Failed to save HTML version: {e}")
            
        except Exception as e:
            logger.exception(f"Error extracting EPUB content: {e}")
        
        return result
    
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download an EPUB document from a URL and save it to permanent storage.
        
        Args:
            url: URL to download from
            
        Returns:
            Tuple of (local file path, metadata)
        """
        metadata = {}
        
        try:
            # Import document storage directory
            from core.document_processor.document_importer import DOCUMENT_STORAGE_DIR
            
            # Generate a unique filename based on URL and timestamp
            filename = f"epub_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(url)}"
            if not filename.endswith('.epub'):
                filename += '.epub'
            
            # Sanitize filename
            filename = ''.join(c for c in filename if c.isalnum() or c in '._-')
            
            # Full path to save the file
            file_path = os.path.join(DOCUMENT_STORAGE_DIR, filename)
            
            # Download the file
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Save the content
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Extract metadata
            metadata = self.extract_metadata(file_path)
            metadata['source_url'] = url
            
            # Attempt to convert EPUB to HTML immediately for better viewing
            try:
                self.extract_content(file_path)
            except Exception as e:
                logger.warning(f"Failed to pre-extract EPUB content: {e}")
            
            return file_path, metadata
            
        except Exception as e:
            logger.exception(f"Error downloading EPUB: {e}")
            return None, metadata


# Update the DocumentView class to handle EPUB content correctly

# This code should be inserted into ui/document_view.py
"""
def _load_epub(self):
    \"\"\"Load EPUB document content.\"\"\"
    try:
        # Use the improved EPUB handler
        from core.document_processor.handlers.epub_handler import EPUBHandler
        
        handler = EPUBHandler()
        content = handler.extract_content(self.document.file_path)
        
        # Use markdown or HTML for display
        display_content = content['markdown'] if content['markdown'] else content['text']
        
        # Set document content
        self.content_text = display_content
        self.content_edit.setMarkdown(display_content) if hasattr(self.content_edit, 'setMarkdown') else self.content_edit.setText(display_content)
        
    except Exception as e:
        logger.exception(f"Error loading EPUB: {e}")
        self.content_edit.setText(f"Error loading EPUB: {str(e)}")
"""
