#!/usr/bin/env python3
# run_fsrs_migration.py

import os
import logging
import appdirs
from migrations.fsrs_migration import migrate_to_fsrs

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Get database path
    data_dir = appdirs.user_data_dir("Incrementum", "Incrementum")
    db_path = os.path.join(data_dir, "incrementum.db")
    
    print(f"Starting FSRS migration for database at: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"Error: Database file not found at {db_path}")
        print("Please run the application at least once to create the database.")
        exit(1)
    
    # Run migration
    success = migrate_to_fsrs(db_path)
    
    if success:
        print("=" * 50)
        print("FSRS Migration Successful!")
        print("=" * 50)
        print("\nYour database has been successfully updated to use the")
        print("Free Spaced Repetition Scheduler (FSRS) algorithm.")
        print("\nBenefits of FSRS:")
        print("- Better retention with fewer reviews")
        print("- More efficient scheduling")
        print("- Adaptive difficulty per item")
        print("- Improved stability tracking")
        print("\nSee docs/FSRS_README.md for more information.")
    else:
        print("=" * 50)
        print("FSRS Migration Failed!")
        print("=" * 50)
        print("\nThere was an error updating your database.")
        print("Please check the logs for details and try again.")
        exit(1) 