#!/usr/bin/env python
# run_web_highlight_color_migration.py

import os
import sys
import logging
from appdirs import user_data_dir

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("web_highlight_migration")

# Import the migration function
from migrations.web_highlight_color_migration import migrate_web_highlight_color

if __name__ == "__main__":
    # Get database path from environment or use default
    data_dir = user_data_dir("Incrementum", "Incrementum")
    db_path = os.path.join(data_dir, "incrementum.db")
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    logger.info(f"Running web highlight color migration on: {db_path}")
    
    # Run migration
    success = migrate_web_highlight_color(db_path)
    
    if success:
        logger.info("✅ Migration completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Migration failed")
        sys.exit(1) 