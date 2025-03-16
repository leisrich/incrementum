# core/document_processor/arxiv_importer.py

import os
import logging
import tempfile
import requests
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

from core.document_processor.processor import DocumentProcessor

logger = logging.getLogger(__name__)

class ArxivImporter:
    """
    Class for searching and importing papers from Arxiv.
    """
    
    # Arxiv API endpoint
    ARXIV_API_URL = "http://export.arxiv.org/api/query"
    
    def __init__(self, document_processor: DocumentProcessor):
        self.document_processor = document_processor
    
    def search_papers(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for papers on Arxiv.
        
        Args:
            query: Search query
            max_results: Maximum number of results to return
            
        Returns:
            List of paper metadata dictionaries
        """
        try:
            # Prepare search parameters
            params = {
                'search_query': query,
                'max_results': max_results,
                'sortBy': 'relevance',
                'sortOrder': 'descending'
            }
            
            # Make API request
            response = requests.get(self.ARXIV_API_URL, params=params)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.content)
            
            # Extract paper info
            papers = []
            
            # Define XML namespaces
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            # Parse entries
            for entry in root.findall('.//atom:entry', ns):
                # Extract basic metadata
                title = entry.find('./atom:title', ns).text.strip()
                summary = entry.find('./atom:summary', ns).text.strip()
                published = entry.find('./atom:published', ns).text.strip()
                
                # Extract authors
                authors = []
                for author in entry.findall('./atom:author/atom:name', ns):
                    authors.append(author.text.strip())
                
                # Extract arxiv ID and links
                arxiv_id = None
                pdf_url = None
                
                # Get ID
                id_element = entry.find('./atom:id', ns)
                if id_element is not None:
                    arxiv_id = id_element.text.strip().split('/')[-1]
                
                # Get PDF link
                for link in entry.findall('./atom:link', ns):
                    if link.get('title') == 'pdf':
                        pdf_url = link.get('href')
                
                # Create paper metadata
                paper = {
                    'title': title,
                    'summary': summary,
                    'authors': authors,
                    'author': ', '.join(authors),  # Combined author string
                    'published': published,
                    'arxiv_id': arxiv_id,
                    'pdf_url': pdf_url
                }
                
                papers.append(paper)
            
            return papers
            
        except Exception as e:
            logger.exception(f"Error searching Arxiv: {e}")
            return []
    
    def import_paper(self, paper_data: Dict[str, Any], category_id: Optional[int] = None) -> Optional[int]:
        """
        Import a paper from Arxiv.
        
        Args:
            paper_data: Paper metadata from search_papers
            category_id: Optional category ID to assign to the document
            
        Returns:
            Document ID if import successful, None otherwise
        """
        try:
            # Check if we have PDF URL
            pdf_url = paper_data.get('pdf_url')
            if not pdf_url:
                logger.error(f"No PDF URL for paper: {paper_data.get('title')}")
                return None
            
            # Create arxiv directory if it doesn't exist
            arxiv_dir = os.path.join(os.getcwd(), 'arxiv')
            os.makedirs(arxiv_dir, exist_ok=True)
            logger.info(f"Using arxiv directory: {arxiv_dir}")
            
            # Download PDF
            logger.info(f"Downloading PDF from {pdf_url}")
            pdf_data = self._download_pdf(pdf_url)
            if not pdf_data:
                logger.error(f"Failed to download PDF: {pdf_url}")
                return None
            
            # Get arxiv ID and create safe filename
            arxiv_id = paper_data.get('arxiv_id', 'unknown')
            title_safe = self._safe_filename(paper_data.get('title', 'unknown'))
            
            # Create a unique filename with both ID and title
            pdf_filename = f"{arxiv_id}_{title_safe}.pdf"
            pdf_path = os.path.join(arxiv_dir, pdf_filename)
            
            logger.info(f"Saving PDF to {pdf_path}")
            with open(pdf_path, 'wb') as f:
                f.write(pdf_data)
            
            # Verify file exists and has content
            if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
                logger.error(f"PDF file not found or empty: {pdf_path}")
                return None
                
            logger.info(f"Importing document from {pdf_path}")
            # Import document
            document = self.document_processor.import_document(pdf_path, category_id)
            
            # Note: We no longer delete the PDF files since they are stored permanently
            
            if document:
                logger.info(f"Successfully imported document with ID: {document.id}")
                return document.id
            else:
                logger.error("Document import failed")
                return None
            
        except Exception as e:
            logger.exception(f"Error importing Arxiv paper: {e}")
            return None
    
    def _download_pdf(self, pdf_url: str) -> Optional[bytes]:
        """
        Download PDF from URL.
        
        Args:
            pdf_url: URL to PDF file
            
        Returns:
            PDF content as bytes if successful, None otherwise
        """
        try:
            # Use a longer timeout for large PDFs
            response = requests.get(pdf_url, stream=True, timeout=30)
            response.raise_for_status()
            
            # Read content
            content = response.content
            
            # Verify we have actual PDF content (check magic bytes)
            if content and len(content) > 4 and content[:4] == b'%PDF':
                return content
            else:
                logger.error(f"Downloaded content is not a valid PDF")
                return None
            
        except Exception as e:
            logger.exception(f"Error downloading PDF: {e}")
            return None
    
    def _safe_filename(self, filename: str) -> str:
        """
        Convert string to safe filename.
        
        Args:
            filename: Input string
            
        Returns:
            Safe filename string
        """
        # Replace unsafe chars
        safe = filename.replace(' ', '_')
        safe = ''.join(c for c in safe if c.isalnum() or c in '_-.')
        
        # Truncate if too long (increased to 100 chars to avoid excessive truncation)
        if len(safe) > 100:
            safe = safe[:100]
        
        return safe
