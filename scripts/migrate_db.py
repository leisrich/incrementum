#!/usr/bin/env python3
"""Script to run database migrations."""

import os
import sys
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from appdirs import user_data_dir

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.utils.settings_manager import SettingsManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_migrations():
    """Run all pending database migrations."""
    logger.info("Running migrations...")
    
    # Get database path from settings
    settings_manager = SettingsManager()
    db_path = settings_manager.get_setting("database", "path", "incrementum.db")
    
    # Create full path to database
    if not os.path.isabs(db_path):
        app_data_dir = user_data_dir('Incrementum', 'Incrementum')
        db_path = os.path.join(app_data_dir, db_path)
    
    logger.info(f"Using database at: {db_path}")
    
    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add YouTube playlist tables
        logger.info("Adding YouTube playlist tables...")
        
        # Create youtube_playlists table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS youtube_playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id VARCHAR(100) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                channel_title VARCHAR(255),
                description TEXT,
                thumbnail_url VARCHAR(512),
                video_count INTEGER DEFAULT 0,
                category_id INTEGER,
                imported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories (id)
            )
        """)
        
        # Create youtube_playlist_videos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS youtube_playlist_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                video_id VARCHAR(20) NOT NULL,
                document_id INTEGER,
                title VARCHAR(255),
                position INTEGER,
                duration INTEGER DEFAULT 0,
                watched_position INTEGER DEFAULT 0,
                watched_percent FLOAT DEFAULT 0.0,
                last_watched TIMESTAMP,
                marked_complete BOOLEAN DEFAULT 0,
                FOREIGN KEY (playlist_id) REFERENCES youtube_playlists (id),
                FOREIGN KEY (document_id) REFERENCES documents (id)
            )
        """)
        
        # Commit changes
        conn.commit()
        logger.info("Migrations completed successfully!")
        
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    run_migrations() 