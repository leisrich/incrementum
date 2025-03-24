#!/usr/bin/env python3

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import Table, Column, Integer, Float, String, Text, DateTime, Boolean, ForeignKey, MetaData
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from core.utils.settings_manager import SettingsManager
from core.knowledge_base.models import Base, VideoLearning

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_migration():
    """Add VideoLearning table to the database."""
    logger.info("Starting video learning migration...")
    
    # Get database path from settings
    settings_manager = SettingsManager()
    db_path = settings_manager.get_setting("database", "path", "incrementum.db")
    
    # Create full path to database
    if not os.path.isabs(db_path):
        app_data_dir = settings_manager.get_app_data_dir()
        db_path = os.path.join(app_data_dir, db_path)
    
    logger.info(f"Using database at: {db_path}")
    
    # Create engine and connect to database
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Check if VideoLearning table already exists
    inspector = inspect_from_engine(engine)
    if 'video_learning' in inspector.get_table_names():
        logger.info("VideoLearning table already exists, skipping migration")
        return
    
    # Create VideoLearning table
    metadata = MetaData()
    video_learning = Table(
        'video_learning', metadata,
        Column('id', Integer, primary_key=True),
        Column('document_id', Integer, ForeignKey('documents.id'), nullable=False),
        Column('current_timestamp', Integer, default=0),
        Column('duration', Integer, default=0),
        Column('last_watched_date', DateTime, default=datetime.utcnow),
        Column('next_watch_date', DateTime, nullable=True),
        Column('watch_priority', Float, default=50.0),
        Column('interval', Integer, default=1),
        Column('repetitions', Integer, default=0),
        Column('easiness', Float, default=2.5),
        Column('schedule_state', String(20), default="new"),
        Column('percent_complete', Float, default=0.0),
        Column('watched_segments', Text, default="[]"),
        Column('playback_rate', Float, default=1.0),
        Column('video_quality', String(20), default="auto")
    )
    
    # Create table
    metadata.create_all(engine)
    logger.info("VideoLearning table created successfully")
    
    # Create session to set up initial data
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Find all video documents without VideoLearning entries
        from sqlalchemy import text
        
        # Get all video documents
        video_docs = session.execute(
            text("""
                SELECT id, title, priority
                FROM documents
                WHERE content_type IN ('mp4', 'video', 'youtube')
                ORDER BY id
            """)
        ).fetchall()
        
        logger.info(f"Found {len(video_docs)} video documents")
        
        # Create VideoLearning entries for each video document
        for doc_id, title, priority in video_docs:
            # Check if entry already exists (shouldn't, but just to be safe)
            exists = session.execute(
                text(f"SELECT id FROM video_learning WHERE document_id = {doc_id}")
            ).fetchone()
            
            if not exists:
                # Insert new entry
                session.execute(
                    text(f"""
                        INSERT INTO video_learning 
                        (document_id, watch_priority, last_watched_date)
                        VALUES 
                        ({doc_id}, {priority}, '{datetime.utcnow().isoformat()}')
                    """)
                )
                logger.info(f"Created VideoLearning entry for document '{title}' (ID: {doc_id})")
        
        # Commit changes
        session.commit()
        logger.info("Migration completed successfully!")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error during migration: {e}")
        raise
    finally:
        session.close()

def inspect_from_engine(engine):
    """Get SQLAlchemy inspector from engine."""
    from sqlalchemy import inspect
    return inspect(engine)

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1) 