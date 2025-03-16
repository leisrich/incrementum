# core/document_processor/handlers/pdf_handler.py

import os
import logging
import tempfile
import requests
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

import PyPDF2
import fitz  # PyMuPDF
from pdfminer.high_level import extract_text, extract_pages
from pdfminer.layout import LTTextContainer, LTChar, LTPage

from .base_handler import DocumentHandler

logger = logging.getLogger(__name__)

class PDFHandler(DocumentHandler):
    """Handler for processing PDF documents."""
    
    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Extract metadata from a PDF document.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary of metadata
        """
        metadata = {
            'title': os.path.basename(file_path),
            'author': '',
            'creation_date': None,
            'modification_date': None,
            'page_count': 0,
            'has_toc': False,
            'has_text_layer': False,
            'needs_ocr': False
        }
        
        try:
            # Use PyPDF2 for basic metadata
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                
                # Extract metadata
                if reader.metadata:
                    if reader.metadata.get('/Title'):
                        metadata['title'] = reader.metadata.get('/Title')
                    if reader.metadata.get('/Author'):
                        metadata['author'] = reader.metadata.get('/Author')
                    if reader.metadata.get('/CreationDate'):
                        metadata['creation_date'] = reader.metadata.get('/CreationDate')
                    if reader.metadata.get('/ModDate'):
                        metadata['modification_date'] = reader.metadata.get('/ModDate')
                
                # Page count
                metadata['page_count'] = len(reader.pages)
                
                # Check for table of contents
                if reader.outline:
                    metadata['has_toc'] = True
            
            # Use PyMuPDF for advanced features
            doc = fitz.open(file_path)
            
            # Check if document has text layer
            has_text = False
            for page in doc:
                if page.get_text():
                    has_text = True
                    break
            
            metadata['has_text_layer'] = has_text
            metadata['needs_ocr'] = not has_text
            
        except Exception as e:
            logger.exception(f"Error extracting PDF metadata: {e}")
        
        return metadata
    
    def extract_content(self, file_path: str) -> Dict[str, Any]:
        """
        Extract content from a PDF document.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary containing extracted content and structure
        """
        result = {
            'text': '',
            'pages': [],
            'toc': [],
            'layout': [],
            'images': []
        }
        
        try:
            # Extract full text using pdfminer
            result['text'] = extract_text(file_path)
            
            # Extract page-by-page content with positions
            pages = []
            for i, page_layout in enumerate(extract_pages(file_path)):
                page_content = {
                    'number': i + 1,
                    'text': '',
                    'elements': []
                }
                
                # Process text elements
                for element in page_layout:
                    if isinstance(element, LTTextContainer):
                        text = element.get_text()
                        page_content['text'] += text
                        
                        # Add element with position
                        page_content['elements'].append({
                            'type': 'text',
                            'content': text,
                            'bbox': (element.x0, element.y0, element.x1, element.y1)
                        })
                
                pages.append(page_content)
            
            result['pages'] = pages
            
            # Extract table of contents using PyMuPDF
            doc = fitz.open(file_path)
            toc = doc.get_toc()
            result['toc'] = toc
            
            # Extract layout information
            layout = []
            for i, page in enumerate(doc):
                page_layout = {
                    'number': i + 1,
                    'width': page.rect.width,
                    'height': page.rect.height,
                    'blocks': []
                }
                
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block["type"] == 0:  # Text block
                        block_data = {
                            'type': 'text',
                            'bbox': block["bbox"],
                            'lines': []
                        }
                        
                        for line in block["lines"]:
                            line_text = ""
                            for span in line["spans"]:
                                line_text += span["text"]
                            
                            block_data['lines'].append({
                                'text': line_text,
                                'bbox': line["bbox"]
                            })
                        
                        page_layout['blocks'].append(block_data)
                    
                    elif block["type"] == 1:  # Image block
                        # Add image info
                        page_layout['blocks'].append({
                            'type': 'image',
                            'bbox': block["bbox"]
                        })
                        
                        # Extract image if needed
                        # (implementation would go here)
                
                layout.append(page_layout)
            
            result['layout'] = layout
            
        except Exception as e:
            logger.exception(f"Error extracting PDF content: {e}")
        
        return result
    
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download a PDF from a URL.
        
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
            fd, temp_path = tempfile.mkstemp(suffix='.pdf')
            
            # Save the content
            with os.fdopen(fd, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Extract metadata
            metadata = self.extract_metadata(temp_path)
            metadata['source_url'] = url
            
            return temp_path, metadata
            
        except Exception as e:
            logger.exception(f"Error downloading PDF: {e}")
            return None, metadata
