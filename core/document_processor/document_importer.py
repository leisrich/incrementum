# core/document_processor/document_importer.py

import os
import logging
import tempfile
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

from sqlalchemy.orm import Session

from core.knowledge_base.models import Document, Category
from core.document_processor.handlers.pdf_handler import PDFHandler
from core.document_processor.handlers.epub_handler import EPUBHandler
from core.document_processor.handlers.html_handler import HTMLHandler
from core.document_processor.handlers.text_handler import TextHandler
from core.document_processor.handlers.docx_handler import DOCXHandler
from core.document_processor.handlers.jina_web_handler import JinaWebHandler
from core.document_processor.handlers.base_handler import DocumentHandler

logger = logging.getLogger(__name__)

class DocumentImporter:
    """Handles importing documents into the system."""
    
    def __init__(self, db_session: Session):
        """Initialize with database session."""
        self.db_session = db_session
        
        # Register handlers
        self.handlers = {
            '.pdf': PDFHandler(),
            '.epub': EPUBHandler(),
            '.html': HTMLHandler(),
            '.htm': HTMLHandler(),
            '.txt': TextHandler(),
            '.docx': DOCXHandler(),
        }
    
    def import_from_file(self, file_path: str, category_id: Optional[int] = None) -> Optional[int]:
        """
        Import a document from a file.
        
        Args:
            file_path: Path to the file
            category_id: Optional category ID to assign
            
        Returns:
            Document ID if successful, None otherwise
        """
        try:
            # Check if file exists
            if not os.path.isfile(file_path):
                logger.error(f"File not found: {file_path}")
                return None
            
            # Get file extension
            _, extension = os.path.splitext(file_path)
            extension = extension.lower()
            
            # Get appropriate handler
            handler = self.handlers.get(extension)
            if not handler:
                logger.error(f"No handler available for file type: {extension}")
                return None
            
            # Extract metadata
            metadata = handler.extract_metadata(file_path)
            
            # Extract content
            content = handler.extract_content(file_path)
            
            # Create document in database
            document = Document(
                title=metadata.get('title', os.path.basename(file_path)),
                author=metadata.get('author', ''),
                file_path=file_path,
                content_type=extension[1:],  # Remove leading dot
                category_id=category_id
            )
            
            # Add document to session
            self.db_session.add(document)
            self.db_session.flush()  # Get ID
            
            # Store additional metadata
            if 'keywords' in metadata and metadata['keywords']:
                # Logic to store keywords as tags
                pass
            
            # Commit changes
            self.db_session.commit()
            
            logger.info(f"Imported document: {document.title} (ID: {document.id})")
            return document.id
            
        except Exception as e:
            logger.exception(f"Error importing document: {e}")
            self.db_session.rollback()
            return None
    
    def import_from_url(self, url: str, category_id: Optional[int] = None, handler: Optional[DocumentHandler] = None) -> Optional[int]:
        """
        Import a document from a URL.
        
        Args:
            url: URL to import from
            category_id: Optional category ID to assign
            handler: Optional specific handler to use, otherwise determined by URL
            
        Returns:
            Document ID if successful, None otherwise
        """
        try:
            # If no handler specified, determine from URL
            if handler is None:
                # Simple extension-based detection
                if url.endswith('.pdf'):
                    handler = self.handlers.get('.pdf')
                elif url.endswith('.epub'):
                    handler = self.handlers.get('.epub')
                elif url.endswith('.txt'):
                    handler = self.handlers.get('.txt')
                elif url.endswith('.docx'):
                    handler = self.handlers.get('.docx')
                else:
                    # Default to HTML handler for standard web pages
                    handler = self.handlers.get('.html')
            
            if not handler:
                logger.error(f"No handler available for URL: {url}")
                return None
            
            # Download the file
            temp_file, metadata = handler.download_from_url(url)
            
            if not temp_file:
                logger.error(f"Failed to download from URL: {url}")
                return None
            
            # Extract content
            content = handler.extract_content(temp_file)
            
            # Create document in database
            document = Document(
                title=metadata.get('title', url),
                author=metadata.get('author', ''),
                file_path=temp_file,
                content_type=metadata.get('source_type', 'web'),
                source_url=url,
                category_id=category_id
            )
            
            # Add document to session
            self.db_session.add(document)
            self.db_session.flush()  # Get ID
            
            # Commit changes
            self.db_session.commit()
            
            logger.info(f"Imported document from URL: {document.title} (ID: {document.id})")
            return document.id
            
        except Exception as e:
            logger.exception(f"Error importing from URL: {e}")
            self.db_session.rollback()
            return None 