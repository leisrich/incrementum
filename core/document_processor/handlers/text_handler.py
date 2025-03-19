# core/document_processor/handlers/text_handler.py

import os
import logging
import tempfile
import requests
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from .base_handler import DocumentHandler

logger = logging.getLogger(__name__)

class TextHandler(DocumentHandler):
    """Handler for processing plain text documents."""
    
    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Extract metadata from a text document.
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Dictionary of metadata
        """
        metadata = {
            'title': os.path.basename(file_path),
            'author': '',
            'creation_date': None,
            'modification_date': None
        }
        
        # For plain text, we don't have much metadata
        # Just use file stats
        try:
            stat = os.stat(file_path)
            metadata['creation_date'] = datetime.fromtimestamp(stat.st_ctime)
            metadata['modification_date'] = datetime.fromtimestamp(stat.st_mtime)
            
        except Exception as e:
            logger.exception(f"Error extracting text metadata: {e}")
        
        return metadata
    
    def extract_content(self, file_path: str) -> Dict[str, Any]:
        """
        Extract content from a text document.
        
        Args:
            file_path: Path to the text file
            
        Returns:
            Dictionary containing extracted content and structure
        """
        result = {
            'text': '',
            'lines': [],
            'paragraphs': []
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Store full text
                result['text'] = content
                
                # Split into lines
                result['lines'] = content.splitlines()
                
                # Split into paragraphs (separated by blank lines)
                result['paragraphs'] = [p for p in content.split('\n\n') if p.strip()]
                
        except Exception as e:
            logger.exception(f"Error extracting text content: {e}")
        
        return result
    
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download a text document from a URL and save it to permanent storage.
        
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
            filename = f"text_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(url)}"
            if not filename.endswith('.txt'):
                filename += '.txt'
            
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
            
            return file_path, metadata
            
        except Exception as e:
            logger.exception(f"Error downloading text: {e}")
            return None, metadata
