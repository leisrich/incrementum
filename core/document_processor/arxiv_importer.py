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
            
            # Download PDF
            pdf_data = self._download_pdf(pdf_url)
            if not pdf_data:
                logger.error(f"Failed to download PDF: {pdf_url}")
                return None
            
            # Save to temporary file
            temp_dir = tempfile.mkdtemp()
            arxiv_id = paper_data.get('arxiv_id', 'unknown')
            title_safe = self._safe_filename(paper_data.get('title', 'unknown'))
            
            # Create a unique filename
            pdf_path = os.path.join(temp_dir, f"{arxiv_id}_{title_safe}.pdf")
            
            with open(pdf_path, 'wb') as f:
                f.write(pdf_data)
            
            # Import document
            document = self.document_processor.import_document(pdf_path, category_id)
            
            # Clean up temporary file
            try:
                os.remove(pdf_path)
                os.rmdir(temp_dir)
            except:
                pass
            
            if document:
                return document.id
            else:
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
            response = requests.get(pdf_url, stream=True)
            response.raise_for_status()
            
            # Read content
            content = response.content
            
            return content
            
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
        
        # Truncate if too long
        if len(safe) > 50:
            safe = safe[:50]
        
        return safe
