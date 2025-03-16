# tests/test_database.py

import unittest
import os
import tempfile
import shutil
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.knowledge_base.models import Base, Document, Category, Extract, LearningItem, Tag, ReviewLog

class TestDatabase(unittest.TestCase):
    """Test cases for database models and relationships."""
    
    def setUp(self):
        """Set up a temporary database for testing."""
        # Create a temporary directory for the test database
        self.temp_dir = tempfile.mkdtemp()
        
        # Create a test database
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        
        # Create tables
        Base.metadata.create_all(self.engine)
        
        # Create a session
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        
        # Create test data
        self._create_test_data()
    
    def tearDown(self):
        """Clean up test database."""
        self.session.close()
        # Remove the temporary directory
        shutil.rmtree(self.temp_dir)
    
    def _create_test_data(self):
        """Create test data for testing."""
        # Create categories
        self.category1 = Category(name="Test Category 1")
        self.category2 = Category(name="Test Category 2")
        self.session.add(self.category1)
        self.session.add(self.category2)
        
        # Create documents
        self.document1 = Document(
            title="Test Document 1",
            author="Test Author",
            content_type="txt",
            file_path="/path/to/test1.txt",
            category=self.category1,
            imported_date=datetime.utcnow(),
            last_accessed=datetime.utcnow()
        )
        self.document2 = Document(
            title="Test Document 2",
            author="Test Author",
            content_type="pdf",
            file_path="/path/to/test2.pdf",
            category=self.category2,
            imported_date=datetime.utcnow(),
            last_accessed=datetime.utcnow()
        )
        self.session.add(self.document1)
        self.session.add(self.document2)
        
        # Create tags
        self.tag1 = Tag(name="test-tag-1")
        self.tag2 = Tag(name="test-tag-2")
        self.session.add(self.tag1)
        self.session.add(self.tag2)
        
        # Add tags to documents
        self.document1.tags.append(self.tag1)
        self.document2.tags.append(self.tag2)
        
        # Create extracts
        self.extract1 = Extract(
            content="Test extract content 1",
            document=self.document1,
            priority=50,
            created_date=datetime.utcnow()
        )
        self.extract2 = Extract(
            content="Test extract content 2",
            document=self.document2,
            priority=75,
            created_date=datetime.utcnow()
        )
        self.session.add(self.extract1)
        self.session.add(self.extract2)
        
        # Add tags to extracts
        self.extract1.tags.append(self.tag1)
        self.extract2.tags.append(self.tag2)
        
        # Create learning items
        self.item1 = LearningItem(
            extract=self.extract1,
            item_type="qa",
            question="Test question 1?",
            answer="Test answer 1",
            priority=50,
            created_date=datetime.utcnow()
        )
        self.item2 = LearningItem(
            extract=self.extract2,
            item_type="cloze",
            question="Test question with [...]",
            answer="cloze",
            priority=75,
            created_date=datetime.utcnow()
        )
        self.session.add(self.item1)
        self.session.add(self.item2)
        
        # Create review logs
        self.review1 = ReviewLog(
            learning_item=self.item1,
            review_date=datetime.utcnow() - timedelta(days=1),
            grade=4,
            response_time=1500,
            scheduled_interval=1,
            actual_interval=1
        )
        self.session.add(self.review1)
        
        # Commit changes
        self.session.commit()
    
    def test_category_relationships(self):
        """Test category relationships."""
        # Test that categories were created
        categories = self.session.query(Category).all()
        self.assertEqual(len(categories), 2)
        
        # Test category-document relationship
        self.assertEqual(len(self.category1.documents), 1)
        self.assertEqual(self.category1.documents[0].title, "Test Document 1")
    
    def test_document_relationships(self):
        """Test document relationships."""
        # Test that documents were created
        documents = self.session.query(Document).all()
        self.assertEqual(len(documents), 2)
        
        # Test document-category relationship
        self.assertEqual(self.document1.category.name, "Test Category 1")
        
        # Test document-tag relationship
        self.assertEqual(len(self.document1.tags), 1)
        self.assertEqual(self.document1.tags[0].name, "test-tag-1")
        
        # Test document-extract relationship
        self.assertEqual(len(self.document1.extracts), 1)
        self.assertEqual(self.document1.extracts[0].content, "Test extract content 1")
    
    def test_extract_relationships(self):
        """Test extract relationships."""
        # Test that extracts were created
        extracts = self.session.query(Extract).all()
        self.assertEqual(len(extracts), 2)
        
        # Test extract-document relationship
        self.assertEqual(self.extract1.document.title, "Test Document 1")
        
        # Test extract-tag relationship
        self.assertEqual(len(self.extract1.tags), 1)
        self.assertEqual(self.extract1.tags[0].name, "test-tag-1")
        
        # Test extract-learning_item relationship
        self.assertEqual(len(self.extract1.learning_items), 1)
        self.assertEqual(self.extract1.learning_items[0].question, "Test question 1?")
    
    def test_learning_item_relationships(self):
        """Test learning item relationships."""
        # Test that learning items were created
        items = self.session.query(LearningItem).all()
        self.assertEqual(len(items), 2)
        
        # Test learning_item-extract relationship
        self.assertEqual(self.item1.extract.content, "Test extract content 1")
        
        # Test learning_item-review_log relationship
        self.assertEqual(len(self.item1.review_history), 1)
        self.assertEqual(self.item1.review_history[0].grade, 4)
    
    def test_cascade_delete(self):
        """Test cascade delete functionality."""
        # Delete a document and check that associated extracts and learning items are deleted
        document_id = self.document1.id
        extract_id = self.extract1.id
        item_id = self.item1.id
        
        self.session.delete(self.document1)
        self.session.commit()
        
        # Check that document is deleted
        document = self.session.query(Document).get(document_id)
        self.assertIsNone(document)
        
        # Check that associated extract is deleted
        extract = self.session.query(Extract).get(extract_id)
        self.assertIsNone(extract)
        
        # Check that associated learning item is deleted
        item = self.session.query(LearningItem).get(item_id)
        self.assertIsNone(item)
    
    def test_tag_relationships(self):
        """Test tag relationships."""
        # Test that tags were created
        tags = self.session.query(Tag).all()
        self.assertEqual(len(tags), 2)
        
        # Test tag-document relationship
        self.assertEqual(len(self.tag1.documents), 1)
        self.assertEqual(self.tag1.documents[0].title, "Test Document 1")
        
        # Test tag-extract relationship
        self.assertEqual(len(self.tag1.extracts), 1)
        self.assertEqual(self.tag1.extracts[0].content, "Test extract content 1")
