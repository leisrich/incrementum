# Auto-generated __init__.py

from core.spaced_repetition.fsrs import FSRSAlgorithm
from core.spaced_repetition.sm18 import SM18Algorithm

# Set the default algorithm to use (FSRS)
DEFAULT_ALGORITHM = FSRSAlgorithm

# For backward compatibility
class FSRSCompatibleSM18(SM18Algorithm):
    """
    Compatibility class that provides an SM18Algorithm interface but uses FSRS under the hood.
    This allows for a smoother transition when upgrading from SM18 to FSRS.
    """
    
    def __init__(self, db_session, *args, **kwargs):
        """Initialize with an FSRS algorithm instance instead of SM18"""
        super().__init__(db_session)
        self.fsrs = FSRSAlgorithm(db_session, *args, **kwargs)
    
    def process_response(self, item_id, grade, response_time=None):
        """Map the SM2 0-5 scale to FSRS rating (1-4) and delegate to FSRS"""
        # Convert SM2 grade (0-5) to FSRS rating (1-4)
        if grade <= 1:  # Complete blackout or familiar but forgotten
            fsrs_rating = 1  # Again
        elif grade == 2:  # Incorrect but easy to recall
            fsrs_rating = 2  # Hard
        elif grade in [3, 4]:  # Correct with effort or hesitation
            fsrs_rating = 3  # Good
        else:  # Perfect response (5)
            fsrs_rating = 4  # Easy
            
        return self.fsrs.process_item_response(item_id, fsrs_rating, response_time)
    
    def get_due_items(self, limit=50, category_id=None):
        """Delegate to FSRS"""
        return self.fsrs.get_due_items(limit, category_id)
        
    def estimate_workload(self, days=7):
        """Provide a backward-compatible workload estimation"""
        # FSRS doesn't have this method by default, so we need to implement it
        workload = {}
        today = datetime.utcnow().date()
        
        for i in range(days):
            target_date = today + timedelta(days=i)
            date_str = target_date.strftime("%Y-%m-%d")
            
            # Count items due on this date
            count = self.db_session.query(LearningItem).filter(
                LearningItem.next_review.between(
                    datetime.combine(target_date, datetime.min.time()),
                    datetime.combine(target_date, datetime.max.time())
                )
            ).count()
            
            workload[date_str] = count
        
        return workload

# Fix missing import for compatibility class
from datetime import datetime, timedelta
from core.knowledge_base.models import LearningItem
