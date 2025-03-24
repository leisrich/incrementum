# core/document_processor/handlers/base_handler.py

from typing import Dict, Any, Optional, List, Tuple
from abc import ABC, abstractmethod

class DocumentHandler(ABC):
    """
    Base class for document handlers.
    All specific document type handlers should inherit from this class.
    """
    
    @abstractmethod
    def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Extract metadata from a document.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Dictionary of metadata
        """
        pass
    
    @abstractmethod
    def extract_content(self, file_path: str) -> Dict[str, Any]:
        """
        Extract content from a document.
        
        Args:
            file_path: Path to the document file
            
        Returns:
            Dictionary containing extracted content and structure
        """
        pass
    
    @abstractmethod
    def download_from_url(self, url: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Download a document from a URL.
        
        Args:
            url: URL to download from
            
        Returns:
            Tuple of (local file path, metadata)
        """
        pass
