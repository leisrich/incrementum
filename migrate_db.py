#!/usr/bin/env python3
# migrate_db.py - Simple script to add the link_url column to RSSFeedEntry table

import os
import sys
import sqlite3
from appdirs import user_data_dir

def main():
    """Add link_url column to RSSFeedEntry table"""
    # Get the database path
    data_dir = user_data_dir("Incrementum", "Incrementum")
    db_path = os.path.join(data_dir, "incrementum.db")
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    print(f"Migrating database at {db_path}")
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if the column already exists
        cursor.execute("PRAGMA table_info(rss_feed_entries)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'link_url' not in columns:
            print("Adding link_url column to rss_feed_entries table...")
            cursor.execute("ALTER TABLE rss_feed_entries ADD COLUMN link_url TEXT")
            
            # Now update existing entries to use entry_id as link_url if it looks like a URL
            cursor.execute("SELECT id, entry_id FROM rss_feed_entries")
            entries = cursor.fetchall()
            
            updates = 0
            for entry_id, entry_id_value in entries:
                if entry_id_value.startswith(('http://', 'https://')):
                    cursor.execute(
                        "UPDATE rss_feed_entries SET link_url = ? WHERE id = ?", 
                        (entry_id_value, entry_id)
                    )
                    updates += 1
                elif ' at ' in entry_id_value:
                    # Handle ZeroHedge and similar sites
                    parts = entry_id_value.split(' at ')
                    if len(parts) == 2 and parts[1].startswith(('http://', 'https://', 'www.')):
                        domain = parts[1]
                        if not domain.startswith(('http://', 'https://')):
                            domain = 'https://' + domain
                        
                        # For ZeroHedge specifically
                        if 'zerohedge.com' in domain.lower():
                            article_id = parts[0].strip()
                            link_url = f"{domain}/news/id/{article_id}"
                            cursor.execute(
                                "UPDATE rss_feed_entries SET link_url = ? WHERE id = ?", 
                                (link_url, entry_id)
                            )
                            updates += 1
            
            print(f"Updated {updates} existing entries with URL data")
            conn.commit()
            print("Migration completed successfully")
        else:
            print("link_url column already exists, no migration needed")
    
    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main() 