# migrations/fsrs_migration.py

import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

def migrate_to_fsrs(db_path):
    """
    Migrate the database to support FSRS algorithm.
    
    This script adds:
    1. A 'reps' column to the documents table
    2. 'stability' and 'reps' columns to the learning_items table
    
    Args:
        db_path: Path to the SQLite database file
    """
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return False
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if migrations are needed
        columns = cursor.execute("PRAGMA table_info(documents)").fetchall()
        column_names = [col[1] for col in columns]
        
        # Migrate documents table if needed
        if "reps" not in column_names:
            logger.info("Adding 'reps' column to documents table")
            cursor.execute("ALTER TABLE documents ADD COLUMN reps INTEGER DEFAULT 0")
        
        # Check learning_items table
        columns = cursor.execute("PRAGMA table_info(learning_items)").fetchall()
        column_names = [col[1] for col in columns]
        
        # Migrate learning_items table if needed
        if "stability" not in column_names:
            logger.info("Adding 'stability' column to learning_items table")
            cursor.execute("ALTER TABLE learning_items ADD COLUMN stability REAL DEFAULT NULL")
        
        if "reps" not in column_names:
            logger.info("Adding 'reps' column to learning_items table")
            cursor.execute("ALTER TABLE learning_items ADD COLUMN reps INTEGER DEFAULT 0")
        
        # Commit changes
        conn.commit()
        
        # Initialize values for existing items
        logger.info("Initializing FSRS values for existing documents")
        cursor.execute("""
            UPDATE documents
            SET reps = reading_count, 
                stability = CASE 
                    WHEN stability IS NULL THEN 0.0
                    ELSE stability
                END
            WHERE reps = 0 AND reading_count > 0
        """)
        
        logger.info("Initializing FSRS values for existing learning items")
        cursor.execute("""
            UPDATE learning_items
            SET reps = repetitions,
                stability = CASE 
                    WHEN easiness > 2.5 THEN easiness * 2
                    WHEN easiness <= 2.5 AND easiness > 1.3 THEN easiness
                    ELSE 1.0
                END
            WHERE reps = 0 AND repetitions > 0
        """)
        
        # Commit final changes
        conn.commit()
        logger.info("Migration to FSRS completed successfully")
        return True
        
    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Get database path from environment or use default
    from appdirs import user_data_dir
    data_dir = user_data_dir("Incrementum", "Incrementum")
    db_path = os.path.join(data_dir, "incrementum.db")
    
    # Run migration
    success = migrate_to_fsrs(db_path)
    if success:
        print(f"Successfully migrated database to FSRS: {db_path}")
    else:
        print(f"Failed to migrate database: {db_path}") 