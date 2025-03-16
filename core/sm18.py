# core/spaced_repetition/sm18.py

import math
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from core.knowledge_base.models import LearningItem, ReviewLog

logger = logging.getLogger(__name__)

class SM18Algorithm:
    """
    Implementation of the SuperMemo SM-18 algorithm for spaced repetition.
    
    This is a simplified version based on publicly available information.
    The actual SM-18 algorithm has additional complexities.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        
        # Algorithm constants
        self.MIN_INTERVAL = 1  # Minimum interval in days
        self.MAX_INTERVAL = 365 * 10  # Maximum interval (10 years)
        self.MIN_EASINESS = 1.3  # Minimum E-factor
        self.DEFAULT_EASINESS = 2.5  # Default E-factor
        
        # Target forgetting index (optimum: around 0.1 = 10% forgetting rate)
        self.TARGET_FORGETTING_INDEX = 0.1
        
        # Grade thresholds
        self.PASS_THRESHOLD = 3  # Grades >= 3 are considered "passed"
    
    def process_response(self, item_id: int, grade: int, response_time: Optional[int] = None) -> Dict[str, Any]:
        """
        Process a response to a learning item and schedule the next repetition.
        
        Args:
            item_id: ID of the learning item
            grade: Grade on a scale from 0 to 5:
                   0 - Complete blackout, wrong response
                   1 - Incorrect response, but upon seeing the answer, it felt familiar
                   2 - Incorrect response, but upon seeing the answer, it was easy to recall
                   3 - Correct response, but required significant effort to recall
                   4 - Correct response, after some hesitation
                   5 - Perfect response, immediate recall
            response_time: Time taken to respond in milliseconds (optional)
            
        Returns:
            Dictionary with scheduling information
        """
        # Retrieve the item
        item = self.db_session.query(LearningItem).get(item_id)
        if not item:
            logger.error(f"Learning item not found: {item_id}")
            return {}
        
        # Calculate time since last review (if applicable)
        actual_interval = None
        if item.last_reviewed:
            actual_interval = (datetime.utcnow() - item.last_reviewed).days
        
        # Record the response
        review_log = ReviewLog(
            learning_item_id=item_id,
            review_date=datetime.utcnow(),
            grade=grade,
            response_time=response_time,
            scheduled_interval=item.interval,
            actual_interval=actual_interval
        )
        self.db_session.add(review_log)
        
        # Calculate new scheduling parameters
        result = self._calculate_new_parameters(item, grade, actual_interval)
        
        # Update the item
        item.interval = result['interval']
        item.easiness = result['easiness']
        item.repetitions = result['repetitions']
        item.last_reviewed = datetime.utcnow()
        item.next_review = result['next_review']
        
        # Update difficulty
        item.difficulty = self._calculate_difficulty(item_id)
        
        # Commit changes
        self.db_session.commit()
        
        return result
    
    def _calculate_new_parameters(self, item: LearningItem, grade: int, actual_interval: Optional[int]) -> Dict[str, Any]:
        """
        Calculate new scheduling parameters based on the response.
        
        Args:
            item: Learning item
            grade: Response grade (0-5)
            actual_interval: Actual interval since last review (or None)
            
        Returns:
            Dictionary with new parameters
        """
        result = {
            'easiness': item.easiness,
            'interval': item.interval,
            'repetitions': item.repetitions,
            'next_review': None,
            'passed': grade >= self.PASS_THRESHOLD
        }
        
        # Calculate new easiness factor (EF)
        delta_ef = 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)
        new_easiness = item.easiness + delta_ef
        
        # Ensure easiness stays within bounds
        result['easiness'] = max(self.MIN_EASINESS, new_easiness)
        
        # Calculate new interval
        if grade < self.PASS_THRESHOLD:  # Failed response
            # Reset repetitions and use shorter interval
            result['repetitions'] = 0
            result['interval'] = self.MIN_INTERVAL
        else:  # Passed response
            # Increment repetitions
            result['repetitions'] = item.repetitions + 1
            
            # Calculate interval based on repetition number
            if result['repetitions'] == 1:
                result['interval'] = self.MIN_INTERVAL
            elif result['repetitions'] == 2:
                result['interval'] = 6  # 6 days for second repetition
            else:
                # Use the SM formula for subsequent repetitions
                result['interval'] = round(item.interval * result['easiness'])
        
        # Ensure interval stays within bounds
        result['interval'] = min(self.MAX_INTERVAL, max(self.MIN_INTERVAL, result['interval']))
        
        # Priority adjustment based on response quality
        # (Implementation would be more complex in a real system)
        
        # Calculate next review date
        result['next_review'] = datetime.utcnow() + timedelta(days=result['interval'])
        
        return result
    
    def _calculate_difficulty(self, item_id: int) -> float:
        """
        Calculate item difficulty based on review history.
        
        Args:
            item_id: ID of the learning item
            
        Returns:
            Difficulty score (0.0-1.0)
        """
        # Get review history
        reviews = self.db_session.query(ReviewLog).filter(
            ReviewLog.learning_item_id == item_id
        ).order_by(ReviewLog.review_date.desc()).limit(10).all()
        
        if not reviews:
            return 0.0
        
        # Calculate average grade (weighted by recency)
        total_weighted_grade = 0.0
        total_weight = 0.0
        
        for i, review in enumerate(reviews):
            # More recent reviews have higher weight
            weight = 1.0 / (i + 1)
            total_weighted_grade += review.grade * weight
            total_weight += weight
        
        avg_grade = total_weighted_grade / total_weight if total_weight > 0 else 0
        
        # Convert to difficulty scale (0-1)
        # 5 = easiest (0.0), 0 = hardest (1.0)
        difficulty = 1.0 - (avg_grade / 5.0)
        
        return difficulty
    
    def get_due_items(self, limit: int = 50, category_id: Optional[int] = None) -> List[LearningItem]:
        """
        Get items due for review based on scheduling.
        
        Args:
            limit: Maximum number of items to return
            category_id: Optional category filter
            
        Returns:
            List of due learning items
        """
        # Base query for due items
        query = self.db_session.query(LearningItem).filter(
            (LearningItem.next_review <= datetime.utcnow()) | 
            (LearningItem.next_review == None)  # New items
        )
        
        # Apply category filter if specified
        if category_id is not None:
            query = query.join(LearningItem.extract).join(Extract.document).filter(
                Document.category_id == category_id
            )
        
        # Order by priority (higher first), then by scheduled review date
        items = query.order_by(
            LearningItem.priority.desc(),
            LearningItem.next_review
        ).limit(limit).all()
        
        return items
    
    def estimate_workload(self, days: int = 7) -> Dict[str, int]:
        """
        Estimate review workload for upcoming days.
        
        Args:
            days: Number of days to estimate
            
        Returns:
            Dictionary mapping dates to number of items due
        """
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
