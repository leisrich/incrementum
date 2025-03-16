#!/usr/bin/env python3
# core/knowledge_base/database_migration.py

import sqlite3
import os
import logging
import glob
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def find_db_file():
    """Find the SQLite database file by searching for it."""
    # Common locations where the database might be
    home_dir = os.path.expanduser("~")
    app_data_locations = [
        os.path.join(home_dir, '.local', 'share', 'Incrementum', 'Incrementum'),
        os.path.join(home_dir, 'AppData', 'Local', 'Incrementum', 'Incrementum'),
        os.path.join(home_dir, 'Library', 'Application Support', 'Incrementum'),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')
    ]
    
    # Look in common locations
    for location in app_data_locations:
        if os.path.exists(location):
            db_path = os.path.join(location, 'incrementum.db')
            if os.path.exists(db_path):
                return db_path
    
    # If not found in common locations, do a search in the user's home directory
    logger.info("Database not found in common locations, searching home directory...")
    for root, dirs, files in os.walk(home_dir):
        for file in files:
            if file == 'incrementum.db':
                db_path = os.path.join(root, file)
                logger.info(f"Found database at: {db_path}")
                return db_path
    
    # If still not found, let's search the entire project directory
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for root, dirs, files in os.walk(current_dir):
        for file in files:
            if file.endswith('.db'):
                db_path = os.path.join(root, file)
                logger.info(f"Found database at: {db_path}")
                return db_path
    
    # If we couldn't find it, return None
    logger.error("Could not find the database file")
    return None

def migrate_database():
    """Apply database migrations to add missing columns."""
    db_path = find_db_file()
    
    if not db_path:
        logger.error("Database file not found")
        return False
    
    logger.info(f"Using database at: {db_path}")
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if priority column exists in documents table
        cursor.execute("PRAGMA table_info(documents)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        # Add missing columns for queue functionality
        if 'priority' not in column_names:
            logger.info("Adding priority column to documents table")
            cursor.execute("ALTER TABLE documents ADD COLUMN priority INTEGER DEFAULT 50")
        
        if 'next_reading_date' not in column_names:
            logger.info("Adding next_reading_date column to documents table")
            cursor.execute("ALTER TABLE documents ADD COLUMN next_reading_date DATETIME")
        
        if 'last_reading_date' not in column_names:
            logger.info("Adding last_reading_date column to documents table")
            cursor.execute("ALTER TABLE documents ADD COLUMN last_reading_date DATETIME")
        
        if 'reading_count' not in column_names:
            logger.info("Adding reading_count column to documents table")
            cursor.execute("ALTER TABLE documents ADD COLUMN reading_count INTEGER DEFAULT 0")
        
        if 'stability' not in column_names:
            logger.info("Adding stability column to documents table")
            cursor.execute("ALTER TABLE documents ADD COLUMN stability FLOAT")
        
        if 'difficulty' not in column_names:
            logger.info("Adding difficulty column to documents table")
            cursor.execute("ALTER TABLE documents ADD COLUMN difficulty FLOAT")
        
        # Commit the changes
        conn.commit()
        logger.info("Database migration completed successfully")
        return True
    
    except Exception as e:
        logger.error(f"Error during database migration: {e}")
        conn.rollback()
        return False
    
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database() 