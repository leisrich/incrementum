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
            logger.error(f"File not found: {file_path}")
            return None
        
        # Determine document type from extension
        _, ext = os.path.splitext(file_path)
        content_type = ext[1:].lower()  # Remove the dot
        
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
    
    def _process_document_content(self, document_id: int) -> None:
        """
        Process document content in the background.
        This is a placeholder - in a real implementation, this would be a background task.
        
        Args:
            document_id: ID of the document to process
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return
        
        try:
            # Get the appropriate handler
            handler = self.handlers[document.content_type]
            
            # Extract content
            content = handler.extract_content(document.file_path)
            
            # Process content (this would be more complex in a real implementation)
            # For now, just update the progress
            document.processing_progress = 100.0
            self.db_session.commit()
            
            logger.info(f"Document processed successfully: {document.title}")
            
        except Exception as e:
            logger.exception(f"Error processing document content: {e}")
            document.processing_progress = -1.0  # Indicate error
            self.db_session.commit()
    
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
