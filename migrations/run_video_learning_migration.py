#!/usr/bin/env python3

"""
Run the video learning migration script to add video learning support
to the Incrementum database.
"""

import os
import sys
from pathlib import Path

# Make sure the script can be run from anywhere
script_dir = Path(__file__).parent
os.chdir(script_dir)

# Add the root directory to Python path
sys.path.insert(0, str(script_dir))

# Import and run the migration
from migrations.video_learning_migration import run_migration

if __name__ == "__main__":
    print("Running video learning migration...")
    run_migration()
    print("Migration completed!") 