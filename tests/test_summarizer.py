#!/usr/bin/env python3
# test_summarizer.py

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from core.knowledge_base.models import Base, Document, Category
from core.document_processor.summarizer import SummarizeDialog

def main():
    # Set up database
    engine = create_engine('sqlite:///incrementum.db', echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db_session = scoped_session(session_factory)
    
    # Check if documents exist
    docs = db_session.query(Document).all()
    print(f"Found {len(docs)} documents:")
    
    if not docs:
        print("No documents found in database. Creating a test document...")
        category = Category(name="Test Category")
        db_session.add(category)
        db_session.flush()
        
        # Create a test document with some sample text
        document = Document(
            title="Test Document",
            file_path="test_document.txt",
            file_size=1000,
            content_type="text",
            category_id=category.id
        )
        db_session.add(document)
        db_session.commit()
        
        # Write some text to the file
        with open("test_document.txt", "w") as f:
            f.write("""# Sample Document for Testing

## Introduction
This is a sample document for testing the summarization feature of Incrementum.
It contains multiple sections and paragraphs to demonstrate the extraction of key sections.

## Background
Summarization is an important feature for knowledge management systems.
It allows users to quickly understand the main points of a document without reading the entire text.
This is especially useful for long documents or when revisiting content after a period of time.

## Methods
There are several approaches to text summarization:
1. Extractive summarization: Selecting key sentences or paragraphs from the original text.
2. Abstractive summarization: Generating new sentences that capture the essence of the content.
3. Hybrid approaches: Combining extractive and abstractive techniques.

## Results
Studies have shown that good summarization tools can save users significant time.
A well-summarized document can convey the same information in 20-30% of the original length.
This efficiency gain translates to better knowledge retention and management.

## Discussion
The effectiveness of summarization depends on several factors:
- The nature of the content
- The purpose of the summary
- The intended audience
- The summarization algorithm used

## Conclusion
Summarization features are a valuable addition to knowledge management tools.
They help users process information more efficiently and focus on the most important aspects.
This test document should provide a good example for the summarization capabilities of Incrementum.
""")
        
        print(f"Created test document with ID {document.id}")
        doc_id = document.id
    else:
        for i, doc in enumerate(docs[:5]):
            print(f"{doc.id}: {doc.title} ({doc.content_type})")
        
        # Use the first document
        doc_id = docs[0].id
    
    # Create QApplication
    app = QApplication(sys.argv)
    
    # Create and show the dialog
    dialog = SummarizeDialog(db_session, doc_id)
    dialog.show()
    
    # Automatically close after 30 seconds for testing
    QTimer.singleShot(30000, app.quit)
    
    # Run the application
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 