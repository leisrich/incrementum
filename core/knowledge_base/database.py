# core/knowledge_base/database.py

import os
import logging
from typing import Optional, Dict, Any
import sqlite3
from datetime import datetime
from contextlib import contextmanager

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy.pool import QueuePool
from appdirs import user_data_dir

# Import the Base and all models for table creation
from core.knowledge_base.models import (
    Base, Category, Document, Tag, 
    Extract, LearningItem, ReviewLog,
    document_tag_association, extract_tag_association
)

logger = logging.getLogger(__name__)

# Global variables
_ENGINE = None
_SESSION_FACTORY = None

def initialize_database(config: Optional[Dict[str, Any]] = None) -> None:
    """
    Initialize the database engine and session factory.
    
    Args:
        config: Optional configuration dictionary with custom settings
    """
    global _ENGINE, _SESSION_FACTORY
    
    try:
        if _ENGINE is not None:
            logger.warning("Database engine already initialized. Skipping initialization.")
            return
        
        # Get application data directory
        data_dir = user_data_dir("Incrementum", "Incrementum")
        os.makedirs(data_dir, exist_ok=True)
        
        # Create database file path
        db_path = os.path.join(data_dir, "incrementum.db")
        
        # Log the database path
        logger.info(f"Using database at: {db_path}")
        
        # Create SQLite URI
        sqlite_uri = f"sqlite:///{db_path}"
        
        # Create engine with custom configuration if provided
        if config and 'engine_options' in config:
            engine_options = config['engine_options']
        else:
            engine_options = {
                'poolclass': QueuePool,
                'pool_size': 5,
                'pool_timeout': 30,
                'pool_recycle': 3600,
                'connect_args': {'check_same_thread': False}
            }
        
        _ENGINE = create_engine(sqlite_uri, **engine_options)
        
        # Configure SQLite for better concurrency and reliability
        @event.listens_for(_ENGINE, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if isinstance(dbapi_connection, sqlite3.Connection):
                cursor = dbapi_connection.cursor()
                
                # Use WAL mode for better concurrency
                cursor.execute("PRAGMA journal_mode=WAL")
                
                # Set synchronous mode (0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA)
                cursor.execute("PRAGMA synchronous=NORMAL")
                
                # For better query performance
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.execute("PRAGMA cache_size=-16000")  # Use 16MB of memory for cache
                
                cursor.close()
        
        # Create all tables if they don't exist
        Base.metadata.create_all(_ENGINE)
        
        # Create session factory
        _SESSION_FACTORY = scoped_session(sessionmaker(bind=_ENGINE))
        
        # Check if database is empty and create initial data if needed
        _create_initial_data()
        
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.exception(f"Error initializing database: {e}")
        raise

def _create_initial_data() -> None:
    """Create initial data if the database is empty."""
    with session_scope() as session:
        # Check if categories table is empty
        category_count = session.query(Category).count()
        
        if category_count == 0:
            logger.info("Creating initial categories")
            
            # Create default categories
            categories = [
                Category(name="General", description="General materials"),
                Category(name="Science", description="Scientific topics"),
                Category(name="Technology", description="Technology topics"),
                Category(name="Mathematics", description="Mathematical topics"),
                Category(name="Languages", description="Language learning"),
                Category(name="History", description="Historical topics")
            ]
            
            # Add subcategories
            subcategories = [
                Category(name="Physics", description="Physics topics", parent=categories[1]),
                Category(name="Biology", description="Biology topics", parent=categories[1]),
                Category(name="Programming", description="Programming topics", parent=categories[2]),
                Category(name="Artificial Intelligence", description="AI topics", parent=categories[2]),
                Category(name="Algebra", description="Algebra topics", parent=categories[3]),
                Category(name="Calculus", description="Calculus topics", parent=categories[3])
            ]
            
            # Add all categories to session
            for category in categories + subcategories:
                session.add(category)
            
            logger.info(f"Created {len(categories)} main categories and {len(subcategories)} subcategories")

def get_engine():
    """Get the database engine, initializing it if necessary."""
    global _ENGINE
    
    if _ENGINE is None:
        initialize_database()
    
    return _ENGINE

def get_session_factory():
    """Get the session factory, initializing it if necessary."""
    global _SESSION_FACTORY
    
    if _SESSION_FACTORY is None:
        initialize_database()
    
    return _SESSION_FACTORY

def create_session() -> Session:
    """Create a new database session."""
    return get_session_factory()()

@contextmanager
def session_scope():
    """
    Provide a transactional scope around a series of operations.
    
    Usage:
        with session_scope() as session:
            session.query(...)
            ...
    """
    session = create_session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception(f"Error in database transaction: {e}")
        raise
    finally:
        session.close()

def get_table_statistics() -> Dict[str, int]:
    """
    Get statistics about the database tables.
    
    Returns:
        Dictionary mapping table names to row counts
    """
    stats = {}
    
    with session_scope() as session:
        # Get all table names
        inspector = inspect(get_engine())
        table_names = inspector.get_table_names()
        
        # Count rows in each table
        for table_name in table_names:
            count = session.execute(f"SELECT COUNT(*) FROM {table_name}").scalar()
            stats[table_name] = count
    
    return stats

def get_db_info() -> Dict[str, Any]:
    """
    Get information about the database.
    
    Returns:
        Dictionary with database information
    """
    engine = get_engine()
    
    info = {
        'dialect': engine.dialect.name,
        'driver': engine.dialect.driver,
        'database': engine.url.database,
        'tables': [],
    }
    
    # Get table info
    inspector = inspect(engine)
    for table_name in inspector.get_table_names():
        columns = [column['name'] for column in inspector.get_columns(table_name)]
        
        info['tables'].append({
            'name': table_name,
            'columns': columns
        })
    
    return info

def vacuum_database() -> None:
    """
    Vacuum the SQLite database to optimize storage and performance.
    """
    engine = get_engine()
    
    # VACUUM is only available for SQLite
    if engine.dialect.name == 'sqlite':
        try:
            with engine.connect() as conn:
                conn.execute("VACUUM")
            logger.info("Database vacuum completed successfully")
        except Exception as e:
            logger.exception(f"Error vacuuming database: {e}")
            raise
    else:
        logger.warning(f"VACUUM operation not supported for {engine.dialect.name} dialect")

def backup_database(backup_path: str) -> bool:
    """
    Create a backup of the database.
    
    Args:
        backup_path: Path to save the backup
        
    Returns:
        True if backup successful, False otherwise
    """
    engine = get_engine()
    
    # Only works for SQLite
    if engine.dialect.name != 'sqlite':
        logger.error(f"Database backup only supported for SQLite, not {engine.dialect.name}")
        return False
    
    try:
        # Get the database file path
        db_path = engine.url.database
        
        # Ensure the backup directory exists
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        
        # Connect to source database
        source = sqlite3.connect(db_path)
        
        # Connect to destination database
        dest = sqlite3.connect(backup_path)
        
        # Copy database
        source.backup(dest)
        
        # Close connections
        source.close()
        dest.close()
        
        logger.info(f"Database backup created: {backup_path}")
        return True
        
    except Exception as e:
        logger.exception(f"Error backing up database: {e}")
        return False

def init_database() -> Session:
    """
    Legacy function for backward compatibility.
    Initialize the database and return a session.
    
    Returns:
        SQLAlchemy session
    """
    initialize_database()
    return create_session()
