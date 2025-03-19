import unittest
import os
import tempfile
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.knowledge_base.models import Base, Extract, LearningItem, ReviewLog
from core.spaced_repetition import FSRSAlgorithm

class TestSpacedRepetition(unittest.TestCase):
    """Test cases for spaced repetition algorithm."""
    
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
        
        # Create algorithm instance
        self.fsrs = FSRSAlgorithm(self.session)
    
    def tearDown(self):
        """Clean up test database."""
        self.session.close()
        # Remove the temporary directory
        os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def _create_test_data(self):
        """Create test data for algorithm testing."""
        # Create test extract
        extract = Extract(
            content="Test extract content",
            context="Test context",
            document_id=1,  # This is just a placeholder for testing
            priority=50,
            created_date=datetime.utcnow()
        )
        self.session.add(extract)
        self.session.commit()
        
        # Create test learning items with varying difficulty
        items = []
        for i in range(10):
            item = LearningItem(
                extract_id=extract.id,
                item_type="qa",
                question=f"Test question {i}",
                answer=f"Test answer {i}",
                priority=50,
                difficulty=0.0,
                created_date=datetime.utcnow()
            )
            self.session.add(item)
            items.append(item)
        
        self.session.commit()
        self.test_items = items
    
    def test_initial_process_response(self):
        """Test initial processing of a response."""
        # Process a response for the first item
        item = self.test_items[0]
        result = self.fsrs.process_item_response(item.id, 3)  # Good response
        
        # Verify the result
        self.assertIsNotNone(result)
        self.assertIn('interval', result)
        self.assertIn('stability', result)
        self.assertIn('difficulty', result)
        self.assertIn('next_review', result)
        
        # Verify that the interval is positive
        self.assertGreater(result['interval'], 0)
        
        # Verify that the item was updated in the database
        updated_item = self.session.query(LearningItem).get(item.id)
        self.assertEqual(updated_item.interval, result['interval'])
        self.assertEqual(updated_item.stability, result['stability'])
        self.assertEqual(updated_item.difficulty, result['difficulty'])
        self.assertEqual(updated_item.next_review, result['next_review'])
    
    def test_repeated_responses(self):
        """Test processing multiple responses for the same item."""
        item = self.test_items[1]
        
        # First response (Good)
        result1 = self.fsrs.process_item_response(item.id, 3)
        interval1 = result1['interval']
        
        # Update the last_reviewed date to simulate time passing
        item.last_reviewed = datetime.utcnow() - timedelta(days=interval1)
        self.session.commit()
        
        # Second response (Easy)
        result2 = self.fsrs.process_item_response(item.id, 4)
        interval2 = result2['interval']
        
        # Interval should increase for an easy response
        self.assertGreater(interval2, interval1)
        
        # Update the last_reviewed date again
        item.last_reviewed = datetime.utcnow() - timedelta(days=interval2)
        self.session.commit()
        
        # Third response (Hard)
        result3 = self.fsrs.process_item_response(item.id, 2)
        interval3 = result3['interval']
        
        # Interval should decrease for a hard response
        self.assertLess(interval3, interval2)
    
    def test_get_due_items(self):
        """Test retrieving due items."""
        # Set up some due items
        now = datetime.utcnow()
        
        # First item: due today
        self.test_items[0].next_review = now - timedelta(hours=1)
        
        # Second item: due tomorrow
        self.test_items[1].next_review = now + timedelta(days=1)
        
        # Third item: due in a week
        self.test_items[2].next_review = now + timedelta(days=7)
        
        # Fourth item: overdue
        self.test_items[3].next_review = now - timedelta(days=3)
        
        # Fifth item: no review date (new)
        self.test_items[4].next_review = None
        
        self.session.commit()
        
        # Get due items
        due_items = self.fsrs.get_due_items()
        
        # Should include items that are due or overdue, plus new items
        self.assertGreaterEqual(len(due_items), 3)  # At least items 0, 3, and 4
        
        # Check that item IDs are in the result
        due_ids = [item.id for item in due_items]
        self.assertIn(self.test_items[0].id, due_ids)  # Due today
        self.assertIn(self.test_items[3].id, due_ids)  # Overdue
        self.assertIn(self.test_items[4].id, due_ids)  # New
        
        # Items not due yet should not be included
        self.assertNotIn(self.test_items[1].id, due_ids)  # Due tomorrow
        self.assertNotIn(self.test_items[2].id, due_ids)  # Due in a week
    
    def test_again_response(self):
        """Test the 'Again' (forgotten) response."""
        item = self.test_items[5]
        
        # First response (Good)
        result1 = self.fsrs.process_item_response(item.id, 3)
        stability1 = result1['stability']
        
        # Update the last_reviewed date
        item.last_reviewed = datetime.utcnow() - timedelta(days=1)
        self.session.commit()
        
        # Second response (Again - forgotten)
        result2 = self.fsrs.process_item_response(item.id, 1)
        stability2 = result2['stability']
        
        # Stability should decrease for a forgotten item
        self.assertLess(stability2, stability1)
        
        # Interval should be reset to a small value
        self.assertLessEqual(result2['interval'], 1)
        
        # Repetition counter should be reset
        self.assertEqual(result2['reps'], 0)

if __name__ == '__main__':
    unittest.main()
