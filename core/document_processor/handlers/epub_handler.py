# core/document_processor/handlers/epub_handler.py

import os
import logging
import tempfile
import requests
import shutil
import zipfile
import chardet
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import html2text

from .base_handler import DocumentHandler

logger = logging.getLogger(__name__)

class EPUBHandler(DocumentHandler):
    """
    Handler for processing EPUB documents with improved character encoding support.
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
        Extract content from an EPUB document with proper character encoding handling.
        
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
            # Create temporary directory for extraction
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Extract EPUB as ZIP
                with zipfile.ZipFile(file_path, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Find content files (HTML)
                html_files = []
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        if file.endswith(('.html', '.xhtml', '.htm')):
                            html_files.append(os.path.join(root, file))
                
                # Process HTML files with proper encoding detection
                all_text = []
                all_html = []
                
                for html_file in sorted(html_files):
                    # Detect encoding
                    with open(html_file, 'rb') as f:
                        raw_data = f.read()
                        detected = chardet.detect(raw_data)
                        encoding = detected['encoding'] or 'utf-8'
                    
                    # Read with detected encoding
                    with open(html_file, 'r', encoding=encoding, errors='replace') as f:
                        html_content = f.read()
                    
                    # Parse HTML
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    # Clean up HTML
                    for script in soup(["script", "style"]):
                        script.extract()
                    
                    # Get text
                    text = soup.get_text(separator='\n\n')
                    all_text.append(text)
                    
                    # Get cleaned HTML
                    clean_html = str(soup)
                    all_html.append(clean_html)
                    
                    # Add chapter
                    result['chapters'].append({
                        'file': os.path.basename(html_file),
                        'html': clean_html,
                        'text': text
                    })
                
                # Combine all content
                result['text'] = '\n\n'.join(all_text)
                result['html'] = '\n\n'.join(all_html)
                
                # Convert to markdown
                h2t = html2text.HTML2Text()
                h2t.ignore_links = False
                h2t.ignore_images = False
                h2t.unicode_snob = True
                result['markdown'] = h2t.handle(result['html'])
                
                # Try to extract TOC using ebooklib as backup
                try:
                    book = epub.read_epub(file_path)
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
                except Exception as e:
                    logger.warning(f"Error extracting TOC with ebooklib: {e}")
            
            finally:
                # Clean up temp directory
                shutil.rmtree(temp_dir)
            
        except Exception as e:
            logger.exception(f"Error extracting EPUB content: {e}")
        
        return result
    
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
            # Download the file
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            # Create a temporary file
            fd, temp_path = tempfile.mkstemp(suffix='.epub')
            
            # Save the content
            with os.fdopen(fd, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Extract metadata
            metadata = self.extract_metadata(temp_path)
            metadata['source_url'] = url
            
            return temp_path, metadata
            
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
