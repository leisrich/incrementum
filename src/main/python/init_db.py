#!/usr/bin/env python3
# init_db.py

import os
import sys
from datetime import datetime
from appdirs import user_data_dir

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.knowledge_base.models import Base, Category, Document, Extract, LearningItem
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def init_database():
    """Initialize the database and create sample data."""
    # Create application data directory if it doesn't exist
    data_dir = user_data_dir("Incrementum", "Incrementum")
    os.makedirs(data_dir, exist_ok=True)
    
    # Create database file
    db_path = os.path.join(data_dir, "incrementum.db")
    engine = create_engine(f"sqlite:///{db_path}")
    
    # Create tables
    Base.metadata.create_all(engine)
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Check if we already have data
    if session.query(Category).count() > 0:
        print(f"Database already exists at {db_path}")
        return
    
    # Create sample categories
    categories = [
        Category(name="Science", description="Scientific topics"),
        Category(name="Technology", description="Technology topics"),
        Category(name="Mathematics", description="Mathematical topics"),
        Category(name="Languages", description="Language learning"),
        Category(name="History", description="Historical topics")
    ]
    
    # Add subcategories
    subcategories = [
        Category(name="Physics", description="Physics topics", parent=categories[0]),
        Category(name="Biology", description="Biology topics", parent=categories[0]),
        Category(name="Programming", description="Programming topics", parent=categories[1]),
        Category(name="Artificial Intelligence", description="AI topics", parent=categories[1]),
        Category(name="Algebra", description="Algebra topics", parent=categories[2]),
        Category(name="Calculus", description="Calculus topics", parent=categories[2])
    ]
    
    # Add all categories to session
    for category in categories + subcategories:
        session.add(category)
    
    # Commit changes
    session.commit()
    
    print(f"Database initialized at {db_path}")
    print(f"Created {len(categories)} main categories and {len(subcategories)} subcategories")

if __name__ == "__main__":
    init_database()
