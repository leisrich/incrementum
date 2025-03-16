import unittest
import os
import tempfile
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.knowledge_base.models import Base, Document, Category, Extract, LearningItem, Tag
from core.knowledge_base.search_engine import SearchEngine

class TestSearchEngine(unittest.TestCase):
    """Test cases for search engine."""
    
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
        
        # Create search engine
        self.search_engine = SearchEngine(self.session)
    
    def tearDown(self):
        """Clean up test database."""
        self.session.close()
        # Remove the temporary directory
        os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def _create_test_data(self):
        """Create test data for testing."""
        # Create categories
        self.category1 = Category(name="Science")
        self.category2 = Category(name="History")
        self.session.add_all([self.category1, self.category2])
        
        # Create tags
        self.tag1 = Tag(name="physics")
        self.tag2 = Tag(name="quantum")
        self.tag3 = Tag(name="ancient")
        self.tag4 = Tag(name="war")
        self.session.add_all([self.tag1, self.tag2, self.tag3, self.tag4])
        
        # Create documents
        self.document1 = Document(
            title="Introduction to Quantum Physics",
            author="Richard Feynman",
            content_type="pdf",
            file_path="/path/to/quantum.pdf",
            category=self.category1,
            imported_date=datetime.utcnow() - timedelta(days=10),
            last_accessed=datetime.utcnow() - timedelta(days=5)
        )
        self.document1.tags.extend([self.tag1, self.tag2])
        
        self.document2 = Document(
            title="Ancient Roman Military Tactics",
            author="Julius Caesar",
            content_type="pdf",
            file_path="/path/to/roman.pdf",
            category=self.category2,
            imported_date=datetime.utcnow() - timedelta(days=5),
            last_accessed=datetime.utcnow() - timedelta(days=1)
        )
        self.document2.tags.extend([self.tag3, self.tag4])
        
        self.session.add_all([self.document1, self.document2])
        
        # Create extracts
        self.extract1 = Extract(
            content="Quantum mechanics is a fundamental theory in physics that provides a description of the physical properties of nature at the scale of atoms and subatomic particles.",
            document=self.document1,
            priority=70,
            created_date=datetime.utcnow() - timedelta(days=9)
        )
        self.extract1.tags.append(self.tag2)
        
        self.extract2 = Extract(
            content="The Roman legion was the largest military unit of the Roman army.",
            document=self.document2,
            priority=60,
            created_date=datetime.utcnow() - timedelta(days=4)
        )
        self.extract2.tags.append(self.tag3)
        
        self.session.add_all([self.extract1, self.extract2])
        
        # Create learning items
        self.item1 = LearningItem(
            extract=self.extract1,
            item_type="qa",
            question="What is quantum mechanics?",
            answer="A fundamental theory in physics that describes physical properties at the atomic and subatomic scale.",
            priority=70,
            created_date=datetime.utcnow() - timedelta(days=8)
        )
        
        self.item2 = LearningItem(
            extract=self.extract2,
            item_type="qa",
            question="What was the largest military unit of the Roman army?",
            answer="The Roman legion.",
            priority=60,
            created_date=datetime.utcnow() - timedelta(days=3)
        )
        
        self.session.add_all([self.item1, self.item2])
        self.session.commit()
    
    def test_search_documents(self):
        """Test searching documents."""
        # Search for "quantum"
        results = self.search_engine.search("quantum", ["document"])
        
        # Should find one document
        self.assertEqual(len(results.get('documents', [])), 1)
        self.assertEqual(results['documents'][0]['title'], "Introduction to Quantum Physics")
        
        # Search for "Roman"
        results = self.search_engine.search("Roman", ["document"])
        
        # Should find one document
        self.assertEqual(len(results.get('documents', [])), 1)
        self.assertEqual(results['documents'][0]['title'], "Ancient Roman Military Tactics")
    
    def test_search_extracts(self):
        """Test searching extracts."""
        # Search for "physics"
        results = self.search_engine.search("physics", ["extract"])
        
        # Should find one extract
        self.assertEqual(len(results.get('extracts', [])), 1)
        self.assertTrue("Quantum mechanics is a fundamental theory in physics" in results['extracts'][0]['content'])
        
        # Search for "Roman"
        results = self.search_engine.search("Roman", ["extract"])
        
        # Should find one extract
        self.assertEqual(len(results.get('extracts', [])), 1)
        self.assertTrue("The Roman legion" in results['extracts'][0]['content'])
    
    def test_search_learning_items(self):
        """Test searching learning items."""
        # Search for "quantum"
        results = self.search_engine.search("quantum", ["learning_item"])
        
        # Should find one learning item
        self.assertEqual(len(results.get('learning_items', [])), 1)
        self.assertEqual(results['learning_items'][0]['question'], "What is quantum mechanics?")
        
        # Search for "Roman"
        results = self.search_engine.search("Roman", ["learning_item"])
        
        # Should find one learning item
        self.assertEqual(len(results.get('learning_items', [])), 1)
        self.assertTrue("Roman" in results['learning_items'][0]['question'])
    
    def test_search_with_filters(self):
        """Test searching with filters."""
        # Search with category filter
        filters = {'category_id': self.category1.id}
        results = self.search_engine.search("", ["document"], filters)
        
        # Should find one document in the Science category
        self.assertEqual(len(results.get('documents', [])), 1)
        self.assertEqual(results['documents'][0]['title'], "Introduction to Quantum Physics")
        
        # Search with tag filter
        filters = {'tags': ["physics"]}
        results = self.search_engine.search("", ["document"], filters)
        
        # Should find one document with the physics tag
        self.assertEqual(len(results.get('documents', [])), 1)
        self.assertEqual(results['documents'][0]['title'], "Introduction to Quantum Physics")
        
        # Search with priority filter
        filters = {'priority_min': 65}
        results = self.search_engine.search("", ["extract"], filters)
        
        # Should find one extract with priority >= 65
        self.assertEqual(len(results.get('extracts', [])), 1)
        self.assertTrue("Quantum mechanics" in results['extracts'][0]['content'])
    
    def test_search_with_complex_query(self):
        """Test searching with complex query syntax."""
        # Search with field syntax
        results = self.search_engine.search('author:Feynman', ["document"])
        
        # Should find one document
        self.assertEqual(len(results.get('documents', [])), 1)
        self.assertEqual(results['documents'][0]['title'], "Introduction to Quantum Physics")
        
        # Search with exact phrase
        results = self.search_engine.search('"Roman legion"', ["extract"])
        
        # Should find one extract
        self.assertEqual(len(results.get('extracts', [])), 1)
        self.assertTrue("The Roman legion" in results['extracts'][0]['content'])
        
        # Search with exclusion
        results = self.search_engine.search('physics NOT atomic', ["extract"])
        
        # Should find no extracts (physics appears with atomic)
        self.assertEqual(len(results.get('extracts', [])), 0)
    
    def test_search_all_entity_types(self):
        """Test searching all entity types."""
        # Search for "Roman" across all entity types
        results = self.search_engine.search("Roman")
        
        # Should find results in all entity types
        self.assertEqual(len(results.get('documents', [])), 1)
        self.assertEqual(len(results.get('extracts', [])), 1)
        self.assertEqual(len(results.get('learning_items', [])), 1)
