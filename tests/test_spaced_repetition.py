import unittest
import os
import tempfile
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.knowledge_base.models import Base, Extract, LearningItem, ReviewLog
from core.spaced_repetition.sm18 import SM18Algorithm

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
        self.sm18 = SM18Algorithm(self.session)
    
    def tearDown(self):
        """Clean up test database."""
        self.session.close()
        # Remove the temporary directory
        os.remove(self.db_path)
        os.rmdir(self.temp_dir)
    
    def _create_test_data(self):
        """Create test data for testing."""
        # Create extract
        self.extract = Extract(
            content="Test extract content",
            priority=50,
            created_date=datetime.utcnow()
        )
        self.session.add(self.extract)
        self.session.flush()
        
        # Create learning items
        self.new_item = LearningItem(
            extract=self.extract,
            item_type="qa",
            question="New item question?",
            answer="New item answer",
            priority=50,
            created_date=datetime.utcnow(),
            interval=0,
            repetitions=0,
            easiness=2.5
        )
        
        self.learned_item = LearningItem(
            extract=self.extract,
            item_type="qa",
            question="Learned item question?",
            answer="Learned item answer",
            priority=50,
            created_date=datetime.utcnow(),
            interval=10,
            repetitions=3,
            easiness=2.5,
            last_reviewed=datetime.utcnow() - timedelta(days=5),
            next_review=datetime.utcnow() + timedelta(days=5)
        )
        
        self.overdue_item = LearningItem(
            extract=self.extract,
            item_type="qa",
            question="Overdue item question?",
            answer="Overdue item answer",
            priority=50,
            created_date=datetime.utcnow(),
            interval=10,
            repetitions=2,
            easiness=2.5,
            last_reviewed=datetime.utcnow() - timedelta(days=15),
            next_review=datetime.utcnow() - timedelta(days=5)
        )
        
        self.session.add_all([self.new_item, self.learned_item, self.overdue_item])
        self.session.commit()
    
    def test_get_due_items(self):
        """Test getting due items."""
        # Should return new and overdue items
        due_items = self.sm18.get_due_items()
        
        self.assertEqual(len(due_items), 2)
        
        # Check that the due items are the new and overdue items
        due_ids = [item.id for item in due_items]
        self.assertIn(self.new_item.id, due_ids)
        self.assertIn(self.overdue_item.id, due_ids)
        self.assertNotIn(self.learned_item.id, due_ids)
    
    def test_process_response_new_item(self):
        """Test processing a response for a new item."""
        # Process a response for the new item with grade 4
        result = self.sm18.process_response(self.new_item.id, 4)
        
        # Verify the result
        self.assertTrue(result['passed'])
        self.assertEqual(result['repetitions'], 1)
        self.assertEqual(result['interval'], 1)  # First interval is always 1 day
        self.assertTrue(result['easiness'] > 2.5)  # Easiness should increase
        
        # Verify the item was updated
        self.session.refresh(self.new_item)
        self.assertEqual(self.new_item.repetitions, 1)
        self.assertEqual(self.new_item.interval, 1)
        self.assertTrue(self.new_item.easiness > 2.5)
        self.assertIsNotNone(self.new_item.last_reviewed)
        self.assertIsNotNone(self.new_item.next_review)
        
        # Verify a review log was created
        review_logs = self.session.query(ReviewLog).filter(
            ReviewLog.learning_item_id == self.new_item.id
        ).all()
        
        self.assertEqual(len(review_logs), 1)
        self.assertEqual(review_logs[0].grade, 4)
    
    def test_process_response_learned_item(self):
        """Test processing a response for a learned item."""
        # Process a response for the learned item with grade 5
        old_easiness = self.learned_item.easiness
        old_interval = self.learned_item.interval
        
        result = self.sm18.process_response(self.learned_item.id, 5)
        
        # Verify the result
        self.assertTrue(result['passed'])
        self.assertEqual(result['repetitions'], 4)
        self.assertTrue(result['interval'] > old_interval)  # Interval should increase
        self.assertTrue(result['easiness'] > old_easiness)  # Easiness should increase
        
        # Verify the item was updated
        self.session.refresh(self.learned_item)
        self.assertEqual(self.learned_item.repetitions, 4)
        self.assertTrue(self.learned_item.interval > old_interval)
        self.assertTrue(self.learned_item.easiness > old_easiness)
    
    def test_process_response_failed(self):
        """Test processing a failed response."""
        # Process a response for the learned item with grade 2 (fail)
        old_easiness = self.learned_item.easiness
        
        result = self.sm18.process_response(self.learned_item.id, 2)
        
        # Verify the result
        self.assertFalse(result['passed'])
        self.assertEqual(result['repetitions'], 0)  # Reset to 0
        self.assertEqual(result['interval'], 1)  # Reset to 1
        self.assertTrue(result['easiness'] < old_easiness)  # Easiness should decrease
        
        # Verify the item was updated
        self.session.refresh(self.learned_item)
        self.assertEqual(self.learned_item.repetitions, 0)
        self.assertEqual(self.learned_item.interval, 1)
        self.assertTrue(self.learned_item.easiness < old_easiness)
    
    def test_estimate_workload(self):
        """Test estimating review workload."""
        # Estimate workload for the next 7 days
        workload = self.sm18.estimate_workload(7)
        
        # Should have at least one day with due items
        self.assertGreater(len(workload), 0)
        
        # At least one day should have 2 items (new + overdue)
        self.assertTrue(any(count >= 2 for count in workload.values()))
