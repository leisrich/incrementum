#!/usr/bin/env python3
"""Script to run database migrations."""

import os
import sys
import logging
from sqlalchemy import create_engine
from core.knowledge_base.migrations import add_youtube_tables

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migrations():
    """Run all pending database migrations."""
    try:
        # Get database URL from environment or use default
        db_url = os.environ.get('DATABASE_URL', 'sqlite:///data/knowledge.db')
        
        # Create engine
        engine = create_engine(db_url)
        
        # Run migrations
        logger.info("Running migrations...")
        
        # Add YouTube tables
        logger.info("Adding YouTube playlist tables...")
        add_youtube_tables.upgrade(engine)
        
        logger.info("Migrations completed successfully!")
        
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        sys.exit(1)

if __name__ == '__main__':
    run_migrations() 