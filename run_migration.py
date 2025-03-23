#!/usr/bin/env python3
# run_migration.py - Standalone script to apply database schema migrations

import os
import sys
import logging
import sqlite3
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
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    ]
    
    # Look in common locations
    for location in app_data_locations:
        if os.path.exists(location):
            db_path = os.path.join(location, 'incrementum.db')
            if os.path.exists(db_path):
                return db_path
    
    # If not found in common locations, look in the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for file in os.listdir(current_dir):
        if file.endswith('.db'):
            db_path = os.path.join(current_dir, file)
            logger.info(f"Found database at: {db_path}")
            return db_path
            
    # If still not found, search the data directory
    data_dir = os.path.join(current_dir, 'data')
    if os.path.exists(data_dir):
        for file in os.listdir(data_dir):
            if file.endswith('.db'):
                db_path = os.path.join(data_dir, file)
                logger.info(f"Found database at: {db_path}")
                return db_path
    
    # If we couldn't find it, return None
    logger.error("Could not find the database file")
    return None

def migrate_highlights_table():
    """Apply database migration to fix the highlights.position column type."""
    db_path = find_db_file()
    
    if not db_path:
        logger.error("Database file not found")
        return False
    
    logger.info(f"Using database at: {db_path}")
    
    # Create a backup of the database first
    backup_path = f"{db_path}.backup-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        # Copy the database file
        with open(db_path, 'rb') as src, open(backup_path, 'wb') as dst:
            dst.write(src.read())
        logger.info(f"Created database backup at: {backup_path}")
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        if not input("Continue without backup? (y/n): ").lower().startswith('y'):
            return False
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if highlights table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='highlights'")
        if not cursor.fetchone():
            logger.info("Highlights table doesn't exist, nothing to migrate")
            return True
        
        # Check column type of position in highlights table
        cursor.execute("PRAGMA table_info(highlights)")
        columns = cursor.fetchall()
        position_column = next((col for col in columns if col[1] == 'position'), None)
        
        if not position_column:
            logger.info("Position column doesn't exist in highlights table")
            
            # Add position column if it doesn't exist
            cursor.execute("ALTER TABLE highlights ADD COLUMN position INTEGER")
            logger.info("Added position column to highlights table")
            conn.commit()
            return True
        
        column_type = position_column[2]
        if column_type == 'INTEGER':
            logger.info("Position column is already INTEGER type, no migration needed")
            return True
            
        logger.info(f"Current position column type: {column_type}, migrating to INTEGER")
        
        # Create a new table with the correct schema
        cursor.execute("""
        CREATE TABLE highlights_new (
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL,
            page_number INTEGER,
            position INTEGER,
            content TEXT NOT NULL,
            color TEXT DEFAULT 'yellow',
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
        """)
        
        # Copy data from old table to new table, converting position where possible
        cursor.execute("""
        INSERT INTO highlights_new (id, document_id, page_number, position, content, color, created_date)
        SELECT id, document_id, page_number, 
            CASE 
                WHEN position IS NULL THEN NULL
                WHEN position = '' THEN NULL
                WHEN CAST(position AS INTEGER) = position THEN CAST(position AS INTEGER)
                ELSE NULL
            END,
            content, color, created_date
        FROM highlights
        """)
        
        # Get row counts before and after
        cursor.execute("SELECT COUNT(*) FROM highlights")
        old_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM highlights_new")
        new_count = cursor.fetchone()[0]
        
        logger.info(f"Migrated {new_count} of {old_count} rows")
        
        # Drop old table and rename new one
        cursor.execute("DROP TABLE highlights")
        cursor.execute("ALTER TABLE highlights_new RENAME TO highlights")
        
        # Commit changes
        conn.commit()
        logger.info("Successfully migrated highlights table")
        return True
        
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    print("Running database migration to fix highlights.position column...")
    if migrate_highlights_table():
        print("Migration completed successfully!")
    else:
        print("Migration failed. Check the logs for details.")
        sys.exit(1) 