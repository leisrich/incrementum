# core/document_processor/processor.py

import os
import logging
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse
from datetime import datetime

# Document handlers
from .handlers.pdf_handler import PDFHandler
from .handlers.html_handler import HTMLHandler
from .handlers.text_handler import TextHandler
from .handlers.epub_handler import EPUBHandler
from .handlers.docx_handler import DOCXHandler
from .handlers.youtube_handler import YouTubeHandler

# Database models
from core.knowledge_base.models import Document, Category
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Main document processing engine that handles importing various document formats."""
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.handlers = {
            'pdf': PDFHandler(),
            'html': HTMLHandler(),
            'txt': TextHandler(),
            'epub': EPUBHandler(),
            'docx': DOCXHandler(),
            'youtube': YouTubeHandler(),
        }
    
    def import_document(self, file_path: str, category_id: Optional[int] = None) -> Optional[Document]:
        """
        Import a document into the system.
        
        Args:
            file_path: Path to the document file
            category_id: Optional category ID to assign to the document
            
        Returns:
            Document object if import successful, None otherwise
        """
        if not os.path.exists(file_path):
            # Special handling for URLs - particularly YouTube
            if file_path.startswith('http'):
                return self.import_from_url(file_path, category_id)
            
            logger.error(f"File not found: {file_path}")
            return None
        
        # Determine document type from extension
        _, ext = os.path.splitext(file_path)
        content_type = ext[1:].lower()  # Remove the dot
        
        # Special handling for EPUB
        if content_type == 'epub':
            # Make sure we use epub handler and content_type
            content_type = 'epub'
        
        # Check if we have a handler for this type
        if content_type not in self.handlers:
            logger.error(f"Unsupported document type: {content_type}")
            return None
        
        try:
            # Use appropriate handler to process the document
            handler = self.handlers[content_type]
            metadata = handler.extract_metadata(file_path)
            
            # Create document record
            document = Document(
                title=metadata.get('title', os.path.basename(file_path)),
                author=metadata.get('author', ''),
                source_url=metadata.get('source_url', ''),
                file_path=file_path,
                content_type=content_type,
                imported_date=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                processing_progress=0.0,
                category_id=category_id
            )
            
            # Add to database
            self.db_session.add(document)
            self.db_session.commit()
            
            # Process the document content in the background
            self._process_document_content(document.id)
            
            return document
            
        except Exception as e:
            logger.exception(f"Error importing document: {e}")
            self.db_session.rollback()
            return None
    
    def _process_document_content(self, document_id: int) -> bool:
        """
        Process the content of a document in the background.
        
        Args:
            document_id: ID of the document to process
            
        Returns:
            True if processing started successfully, False otherwise
        """
        # For now, just retrieve document for context
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return False
        
        try:
            # Mark processing as started
            document.processing_progress = 10.0
            self.db_session.commit()
            
            # TODO: Implement background processing logic
            # This would extract text, generate thumbnails, etc.
            
            # Mark as complete
            document.processing_progress = 100.0
            self.db_session.commit()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error processing document: {e}")
            document.processing_progress = -1.0  # Error state
            self.db_session.commit()
            return False
    
    def import_from_url(self, url: str, category_id: Optional[int] = None) -> Optional[Document]:
        """
        Import a document from a URL.
        
        Args:
            url: URL to import from
            category_id: Optional category ID to assign to the document
            
        Returns:
            Document object if import successful, None otherwise
        """
        # Parse URL to determine type
        parsed_url = urlparse(url)
        path = parsed_url.path
        _, ext = os.path.splitext(path)
        
        # Determine content type
        content_type = 'html'  # Default to HTML
        if ext:
            ext_type = ext[1:].lower()
            if ext_type in self.handlers:
                content_type = ext_type
        
        # Check for YouTube URLs
        if 'youtube.com' in parsed_url.netloc or 'youtu.be' in parsed_url.netloc:
            content_type = 'youtube'
        
        try:
            # Download the content
            handler = self.handlers[content_type]
            local_path, metadata = handler.download_from_url(url)
            
            if not local_path:
                logger.error(f"Failed to download from URL: {url}")
                return None
            
            # Create document record
            document = Document(
                title=metadata.get('title', url),
                author=metadata.get('author', ''),
                source_url=url,
                file_path=local_path,
                content_type=content_type,
                imported_date=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                processing_progress=0.0,
                category_id=category_id
            )
            
            # Add to database
            self.db_session.add(document)
            self.db_session.commit()
            
            # Process the document content in the background
            self._process_document_content(document.id)
            
            return document
            
        except Exception as e:
            logger.exception(f"Error importing from URL: {e}")
            return None
