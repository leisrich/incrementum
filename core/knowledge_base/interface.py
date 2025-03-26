"""
Interface for knowledge base operations.

This module provides high-level functions for operations on the knowledge base,
including document and category management.
"""

import os
import logging
from typing import List, Dict, Any, Optional, Union
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from core.knowledge_base.models import Document, Category
from core.knowledge_base.database import create_session, close_session

logger = logging.getLogger(__name__)

def get_all_categories(session: Optional[Session] = None) -> List[Dict[str, Any]]:
    """
    Get all categories from the database.
    
    Args:
        session: Optional database session (creates one if not provided)
        
    Returns:
        List of category dictionaries
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True
    
    try:
        categories = session.query(Category).all()
        result = [category.to_dict() for category in categories]
        return result
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching categories: {e}")
        return []
    finally:
        if close_session_after and session:
            close_session(session)

def get_category_by_id(category_id: int, session: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    """
    Get a category by its ID.
    
    Args:
        category_id: ID of the category to retrieve
        session: Optional database session (creates one if not provided)
        
    Returns:
        Category dictionary or None if not found
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True
    
    try:
        category = session.query(Category).filter(Category.id == category_id).first()
        if category:
            return category.to_dict()
        return None
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching category {category_id}: {e}")
        return None
    finally:
        if close_session_after and session:
            close_session(session)

def create_category(name: str, description: str = "", parent_id: Optional[int] = None, 
                   session: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    """
    Create a new category.
    
    Args:
        name: Name of the category
        description: Optional description
        parent_id: Optional parent category ID
        session: Optional database session (creates one if not provided)
        
    Returns:
        New category dictionary or None if creation failed
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True
    
    try:
        category = Category(
            name=name,
            description=description,
            parent_id=parent_id
        )
        session.add(category)
        session.commit()
        return category.to_dict()
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception(f"Error creating category '{name}': {e}")
        return None
    finally:
        if close_session_after and session:
            close_session(session)

def assign_document_to_category(document_id: int, category_id: int, 
                               session: Optional[Session] = None) -> bool:
    """
    Assign a document to a category.
    
    Args:
        document_id: ID of the document
        category_id: ID of the category
        session: Optional database session (creates one if not provided)
        
    Returns:
        True if assignment was successful, False otherwise
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True
    
    try:
        document = session.query(Document).filter(Document.id == document_id).first()
        category = session.query(Category).filter(Category.id == category_id).first()
        
        if not document:
            logger.error(f"Document with ID {document_id} not found")
            return False
        
        if not category:
            logger.error(f"Category with ID {category_id} not found")
            return False
        
        # Assign document to category if not already assigned
        if category not in document.categories:
            document.categories.append(category)
            session.commit()
            logger.info(f"Document '{document.title}' assigned to category '{category.name}'")
            return True
        else:
            logger.info(f"Document '{document.title}' already in category '{category.name}'")
            return True
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception(f"Error assigning document {document_id} to category {category_id}: {e}")
        return False
    finally:
        if close_session_after and session:
            close_session(session)

def remove_document_from_category(document_id: int, category_id: int, 
                                 session: Optional[Session] = None) -> bool:
    """
    Remove a document from a category.
    
    Args:
        document_id: ID of the document
        category_id: ID of the category
        session: Optional database session (creates one if not provided)
        
    Returns:
        True if removal was successful, False otherwise
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True
    
    try:
        document = session.query(Document).filter(Document.id == document_id).first()
        category = session.query(Category).filter(Category.id == category_id).first()
        
        if not document:
            logger.error(f"Document with ID {document_id} not found")
            return False
        
        if not category:
            logger.error(f"Category with ID {category_id} not found")
            return False
        
        # Remove document from category if assigned
        if category in document.categories:
            document.categories.remove(category)
            session.commit()
            logger.info(f"Document '{document.title}' removed from category '{category.name}'")
            return True
        else:
            logger.info(f"Document '{document.title}' not in category '{category.name}'")
            return True
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception(f"Error removing document {document_id} from category {category_id}: {e}")
        return False
    finally:
        if close_session_after and session:
            close_session(session)

def get_document_by_id(document_id: int, session: Optional[Session] = None) -> Optional[Dict[str, Any]]:
    """
    Get a document by its ID.
    
    Args:
        document_id: ID of the document to retrieve
        session: Optional database session (creates one if not provided)
        
    Returns:
        Document dictionary or None if not found
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True
    
    try:
        document = session.query(Document).filter(Document.id == document_id).first()
        if document:
            return document.to_dict()
        return None
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching document {document_id}: {e}")
        return None
    finally:
        if close_session_after and session:
            close_session(session)

def get_all_documents(session: Optional[Session] = None) -> List[Dict[str, Any]]:
    """
    Get all documents from the database.

    Args:
        session: Optional database session (creates one if not provided)

    Returns:
        List of document dictionaries
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True

    try:
        documents = session.query(Document).all()
        result = [document.to_dict() for document in documents]
        return result
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching documents: {e}")
        return []
    finally:
        if close_session_after and session:
            close_session(session)

def get_document_metadata(document_id: int, session: Optional[Session] = None) -> Optional[str]:
    """
    Get a document's metadata.
    
    Args:
        document_id: ID of the document
        session: Optional database session (creates one if not provided)
        
    Returns:
        Document metadata or None if not found
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True
    
    try:
        document = session.query(Document).filter(Document.id == document_id).first()
        if document:
            return document.doc_metadata
        return None
    except SQLAlchemyError as e:
        logger.exception(f"Error fetching document metadata for {document_id}: {e}")
        return None
    finally:
        if close_session_after and session:
            close_session(session)

def update_document_metadata(document_id: int, metadata: str, session: Optional[Session] = None) -> bool:
    """
    Update a document's metadata.
    
    Args:
        document_id: ID of the document
        metadata: New metadata string (JSON)
        session: Optional database session (creates one if not provided)
        
    Returns:
        True if update was successful, False otherwise
    """
    close_session_after = False
    if session is None:
        session = create_session()
        close_session_after = True
    
    try:
        document = session.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error(f"Document with ID {document_id} not found")
            return False
        
        document.doc_metadata = metadata
        session.commit()
        logger.info(f"Updated metadata for document {document_id}")
        return True
    except SQLAlchemyError as e:
        session.rollback()
        logger.exception(f"Error updating metadata for document {document_id}: {e}")
        return False
    finally:
        if close_session_after and session:
            close_session(session) 
