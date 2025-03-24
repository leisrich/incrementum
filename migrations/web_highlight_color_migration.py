# migrations/web_highlight_color_migration.py

import logging
import os
import sqlite3
from datetime import datetime

logger = logging.getLogger(__name__)

def migrate_web_highlight_color(db_path):
    """
    Add color column to web_highlights table.
    
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
        # Check if migration is needed
        columns = cursor.execute("PRAGMA table_info(web_highlights)").fetchall()
        column_names = [col[1] for col in columns]
        
        # Migrate web_highlights table if needed
        if "color" not in column_names:
            logger.info("Adding 'color' column to web_highlights table")
            cursor.execute("ALTER TABLE web_highlights ADD COLUMN color VARCHAR(50) DEFAULT 'yellow'")
            
            # Set default color for existing highlights
            cursor.execute("UPDATE web_highlights SET color = 'yellow' WHERE color IS NULL")
        
        # Commit changes
        conn.commit()
        logger.info("Migration for web_highlights color completed successfully")
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
    success = migrate_web_highlight_color(db_path)
    if success:
        print(f"Successfully added color column to web_highlights table: {db_path}")
    else:
        print(f"Failed to update web_highlights table: {db_path}") 