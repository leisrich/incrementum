#!/usr/bin/env python3
# core/spaced_repetition/item_analyzer.py - Analytics for spaced repetition items

import logging
from datetime import datetime, timedelta
import numpy as np
import math
from sqlalchemy import func, desc, and_
from sqlalchemy.orm import Session

from core.knowledge_base.models import LearningItem, ReviewLog

logger = logging.getLogger(__name__)

class ItemQualityAnalyzer:
    """
    Analyzes learning items to determine their quality metrics.
    Used for data-driven insights into the learning process.
    """
    
    def __init__(self, db_session):
        """Initialize with database session."""
        self.db_session = db_session
        
    def get_item_performance_metrics(self, item_id):
        """
        Get comprehensive performance metrics for a specific item.
        
        Args:
            item_id: ID of the learning item
            
        Returns:
            dict: Performance metrics
        """
        item = self.db_session.query(LearningItem).get(item_id)
        if not item:
            logger.warning(f"Item {item_id} not found")
            return None
            
        # Get review history
        reviews = self.db_session.query(ReviewLog).filter(
            ReviewLog.learning_item_id == item_id
        ).order_by(ReviewLog.review_date).all()
        
        if not reviews:
            logger.info(f"No review history for item {item_id}")
            return {
                "id": item_id,
                "total_reviews": 0,
                "success_rate": 0,
                "average_interval": 0,
                "retention_rate": 0,
                "response_times": [],
                "is_leech": False,
                "difficulty_trend": "new"
            }
            
        # Calculate metrics
        total_reviews = len(reviews)
        successful_reviews = sum(1 for r in reviews if r.grade >= 3)
        success_rate = successful_reviews / total_reviews if total_reviews > 0 else 0
        
        # Calculate intervals between reviews
        intervals = []
        prev_date = None
        for r in reviews:
            if prev_date:
                interval = (r.review_date - prev_date).days
                intervals.append(interval)
            prev_date = r.review_date
            
        avg_interval = sum(intervals) / len(intervals) if intervals else 0
        
        # Calculate response times
        response_times = [r.response_time for r in reviews if r.response_time]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        # Determine if item is a leech (many failed reviews)
        failed_recently = sum(1 for r in reviews[-5:] if r.grade < 3)
        is_leech = failed_recently >= 3
        
        # Analyze difficulty trend
        if len(reviews) >= 3:
            recent_grades = [r.grade for r in reviews[-3:]]
            if all(g >= 4 for g in recent_grades):
                difficulty_trend = "easy"
            elif all(g <= 2 for g in recent_grades):
                difficulty_trend = "difficult"
            else:
                difficulty_trend = "mixed"
        else:
            difficulty_trend = "new"
            
        # Calculate retention rate based on scheduled intervals
        retention_stats = self._calculate_retention_stats(reviews)
            
        return {
            "id": item_id,
            "total_reviews": total_reviews,
            "success_rate": success_rate,
            "average_interval": avg_interval,
            "average_response_time": avg_response_time,
            "response_times": response_times,
            "retention_rate": retention_stats["retention_rate"],
            "predicted_recall": retention_stats["predicted_recall"],
            "is_leech": is_leech,
            "difficulty_trend": difficulty_trend,
            "optimal_interval": retention_stats["optimal_interval"]
        }
        
    def _calculate_retention_stats(self, reviews):
        """Calculate retention statistics from review history."""
        if not reviews or len(reviews) < 2:
            return {
                "retention_rate": 0,
                "predicted_recall": 0,
                "optimal_interval": 1
            }
            
        # Get actual vs scheduled intervals
        scheduled_intervals = []
        actual_intervals = []
        correct_recalls = []
        
        prev_review = None
        for review in reviews:
            if prev_review and hasattr(prev_review, 'scheduled_interval'):
                scheduled_interval = prev_review.scheduled_interval
                if scheduled_interval:
                    actual_interval = (review.review_date - prev_review.review_date).days
                    scheduled_intervals.append(scheduled_interval)
                    actual_intervals.append(actual_interval)
                    correct_recalls.append(1 if review.grade >= 3 else 0)
            prev_review = review
                
        if not scheduled_intervals:
            return {
                "retention_rate": 0,
                "predicted_recall": 0,
                "optimal_interval": 1
            }
            
        # Calculate retention rate
        retention_rate = sum(correct_recalls) / len(correct_recalls)
        
        # Calculate optimal interval based on stability
        if hasattr(reviews[-1], 'stability') and reviews[-1].stability:
            stability = reviews[-1].stability
            optimal_interval = -stability * math.log(0.9)  # Target 90% retention
        else:
            # Simplified estimate based on performance
            avg_interval = sum(actual_intervals) / len(actual_intervals)
            optimal_interval = avg_interval * (retention_rate + 0.1)
            
        # Predict recall probability for next review
        days_since_last = (datetime.utcnow() - reviews[-1].review_date).days
        if hasattr(reviews[-1], 'stability') and reviews[-1].stability:
            predicted_recall = math.exp(-days_since_last / reviews[-1].stability)
        else:
            # Simplified estimate
            predicted_recall = max(0, 1 - (days_since_last / (optimal_interval * 2)))
            
        return {
            "retention_rate": retention_rate,
            "predicted_recall": predicted_recall,
            "optimal_interval": max(1, round(optimal_interval))
        }
        
    def get_item_difficulty(self, item_id):
        """
        Estimate item difficulty based on review history.
        
        Args:
            item_id: ID of the learning item
            
        Returns:
            float: Difficulty score (0-1, where 1 is most difficult)
        """
        reviews = self.db_session.query(ReviewLog).filter(
            ReviewLog.learning_item_id == item_id
        ).order_by(ReviewLog.review_date).all()
        
        if not reviews:
            return 0.5  # Default medium difficulty
            
        # Weight more recent reviews higher
        weights = np.linspace(0.5, 1.0, len(reviews))
        
        # Convert grades to difficulties (1-5 grade → 1.0-0.0 difficulty)
        difficulties = [max(0, 1 - (r.grade / 5)) for r in reviews]
        
        # Calculate weighted average
        difficulty = sum(d * w for d, w in zip(difficulties, weights)) / sum(weights)
        
        # Consider response times as a factor
        response_times = [r.response_time for r in reviews if r.response_time]
        if response_times:
            avg_time = sum(response_times) / len(response_times)
            # Normalize to a factor between 0.8 and 1.2
            time_factor = 0.8 + (min(avg_time, 15000) / 15000) * 0.4
            difficulty *= time_factor
            
        return min(1.0, max(0.0, difficulty))
        
    def analyze_learning_session(self, user_id=None, days=7):
        """
        Analyze recent learning sessions for insights.
        
        Args:
            user_id: Optional user ID for multi-user systems
            days: Number of days to analyze
            
        Returns:
            dict: Session analytics
        """
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Query recent reviews
        reviews_query = self.db_session.query(ReviewLog).filter(
            ReviewLog.review_date >= start_date
        )
        
        # Apply user filter if provided (implement user filtering if needed)
        # if user_id is not None:
        #     reviews_query = reviews_query.join(LearningItem).filter(LearningItem.user_id == user_id)
            
        reviews = reviews_query.order_by(ReviewLog.review_date).all()
        
        if not reviews:
            logger.info("No reviews found in the specified period")
            return {
                "total_reviews": 0,
                "daily_average": 0,
                "success_rate": 0,
                "review_time_data": []
            }
            
        # Calculate daily review counts
        daily_counts = {}
        for r in reviews:
            day = r.review_date.date()
            daily_counts[day] = daily_counts.get(day, 0) + 1
            
        # Calculate success rate
        successful = sum(1 for r in reviews if r.grade >= 3)
        success_rate = successful / len(reviews)
        
        # Analyze review times
        review_times = []
        for day, count in daily_counts.items():
            review_times.append({
                "date": day.isoformat(),
                "count": count
            })
            
        # Calculate improvement trend
        if len(reviews) >= 10:
            first_half = reviews[:len(reviews)//2]
            second_half = reviews[len(reviews)//2:]
            first_success = sum(1 for r in first_half if r.grade >= 3) / len(first_half)
            second_success = sum(1 for r in second_half if r.grade >= 3) / len(second_half)
            improvement = second_success - first_success
        else:
            improvement = 0
            
        return {
            "total_reviews": len(reviews),
            "daily_average": len(reviews) / min(days, len(daily_counts)),
            "success_rate": success_rate,
            "improvement_trend": improvement,
            "review_time_data": review_times
        }
        
    def get_learning_efficiency(self, item_ids=None):
        """
        Calculate learning efficiency metrics for items.
        
        Args:
            item_ids: Optional list of item IDs to analyze, or None for all items
            
        Returns:
            dict: Efficiency metrics
        """
        if item_ids:
            items = self.db_session.query(LearningItem).filter(
                LearningItem.id.in_(item_ids)
            ).all()
        else:
            items = self.db_session.query(LearningItem).all()
            
        if not items:
            return {
                "average_reviews_to_learn": 0,
                "retention_vs_interval": []
            }
            
        item_metrics = []
        for item in items:
            reviews = self.db_session.query(ReviewLog).filter(
                ReviewLog.learning_item_id == item.id
            ).order_by(ReviewLog.review_date).all()
            
            if reviews:
                # Calculate reviews to "learned" state
                reviews_to_learn = 0
                learned = False
                for i, r in enumerate(reviews):
                    reviews_to_learn = i + 1
                    if r.grade >= 4:
                        learned = True
                        break
                        
                if not learned:
                    reviews_to_learn = 0
                    
                # Calculate interval vs retention relationship
                intervals = []
                retentions = []
                prev_review = None
                for r in reviews:
                    if prev_review:
                        interval = (r.review_date - prev_review.review_date).days
                        intervals.append(interval)
                        retentions.append(1 if r.grade >= 3 else 0)
                    prev_review = r
                    
                item_metrics.append({
                    "id": item.id,
                    "reviews_to_learn": reviews_to_learn,
                    "intervals": intervals,
                    "retentions": retentions
                })
                
        # Calculate average reviews to learn
        valid_counts = [m["reviews_to_learn"] for m in item_metrics if m["reviews_to_learn"] > 0]
        avg_reviews = sum(valid_counts) / len(valid_counts) if valid_counts else 0
        
        # Aggregate interval vs retention data
        interval_retention = {}
        for m in item_metrics:
            for interval, retention in zip(m["intervals"], m["retentions"]):
                # Group intervals by range
                interval_range = min(10, max(1, (interval // 5) * 5))
                if interval_range not in interval_retention:
                    interval_retention[interval_range] = {"total": 0, "correct": 0}
                interval_retention[interval_range]["total"] += 1
                interval_retention[interval_range]["correct"] += retention
                
        # Calculate retention rate by interval
        retention_vs_interval = []
        for interval, data in sorted(interval_retention.items()):
            if data["total"] > 0:
                retention_rate = data["correct"] / data["total"]
                retention_vs_interval.append({
                    "interval": interval,
                    "retention_rate": retention_rate,
                    "sample_size": data["total"]
                })
                
        return {
            "average_reviews_to_learn": avg_reviews,
            "retention_vs_interval": retention_vs_interval
        }

        
class LeechAnalyzer:
    """
    Detects and manages problematic items (leeches) in spaced repetition systems.
    Leeches are items that consume disproportionate time and effort to learn.
    """
    
    def __init__(self, db_session):
        """Initialize with database session."""
        self.db_session = db_session
        
        # Default configuration
        self.config = {
            "leech_threshold": 5,         # Number of failures to consider an item a leech
            "recent_reviews_window": 10,  # Number of most recent reviews to analyze
            "max_fail_ratio": 0.4,        # Maximum ratio of failures to consider an item a leech
            "consecutive_fails": 3        # Number of consecutive failures to consider an item a leech
        }
        
    def update_config(self, new_config):
        """Update configuration."""
        if not isinstance(new_config, dict):
            raise ValueError("Configuration must be a dictionary")
        self.config.update(new_config)
        
    def detect_leeches(self, item_ids=None):
        """
        Detect leech items that require special attention.
        
        Args:
            item_ids: Optional list of item IDs to check, or None for all items
            
        Returns:
            list: List of leech items with analysis data
        """
        # Get items to analyze
        if item_ids:
            items = self.db_session.query(LearningItem).filter(
                LearningItem.id.in_(item_ids)
            ).all()
        else:
            # Get items with enough review history
            items = self.db_session.query(LearningItem).filter(
                LearningItem.id.in_(
                    self.db_session.query(ReviewLog.learning_item_id)
                    .group_by(ReviewLog.learning_item_id)
                    .having(func.count(ReviewLog.id) >= 3)
                )
            ).all()
            
        leeches = []
        
        for item in items:
            # Get review history
            reviews = self.db_session.query(ReviewLog).filter(
                ReviewLog.learning_item_id == item.id
            ).order_by(ReviewLog.review_date).all()
            
            if not reviews:
                continue
                
            # Apply different leech detection algorithms
            leech_data = {}
            is_leech = False
            
            # Method 1: Count total failures
            total_failures = sum(1 for r in reviews if r.grade < 3)
            if total_failures >= self.config["leech_threshold"]:
                is_leech = True
                leech_data["total_failures"] = total_failures
                
            # Method 2: Analyze most recent reviews
            recent_reviews = reviews[-min(len(reviews), self.config["recent_reviews_window"]):]
            recent_failures = sum(1 for r in recent_reviews if r.grade < 3)
            recent_fail_ratio = recent_failures / len(recent_reviews)
            if recent_fail_ratio >= self.config["max_fail_ratio"]:
                is_leech = True
                leech_data["recent_fail_ratio"] = recent_fail_ratio
                
            # Method 3: Check for consecutive failures
            max_consecutive_fails = 0
            current_consecutive = 0
            for r in reviews:
                if r.grade < 3:
                    current_consecutive += 1
                    max_consecutive_fails = max(max_consecutive_fails, current_consecutive)
                else:
                    current_consecutive = 0
                    
            if max_consecutive_fails >= self.config["consecutive_fails"]:
                is_leech = True
                leech_data["max_consecutive_fails"] = max_consecutive_fails
                
            # If identified as a leech, add to the list
            if is_leech:
                leeches.append({
                    "item_id": item.id,
                    "item_type": item.item_type,
                    "question": item.question,
                    "answer": item.answer,
                    "total_reviews": len(reviews),
                    "first_reviewed": reviews[0].review_date,
                    "last_reviewed": reviews[-1].review_date,
                    "leech_data": leech_data
                })
                
        return leeches
        
    def suggest_leech_treatments(self, leech_items):
        """
        Suggest treatments for leech items.
        
        Args:
            leech_items: List of leech items from detect_leeches()
            
        Returns:
            dict: Item IDs mapped to suggested treatments
        """
        treatments = {}
        
        for leech in leech_items:
            item_id = leech["item_id"]
            
            # Get additional data about the item
            reviews = self.db_session.query(ReviewLog).filter(
                ReviewLog.learning_item_id == item_id
            ).order_by(ReviewLog.review_date).all()
            
            leech_data = leech["leech_data"]
            
            # Analyze the leech pattern
            avg_response_time = sum(r.response_time for r in reviews if r.response_time) / sum(1 for r in reviews if r.response_time) if any(r.response_time for r in reviews) else 0
            
            # Choose treatment strategy based on the analysis
            if "max_consecutive_fails" in leech_data and leech_data["max_consecutive_fails"] >= 4:
                # Severe leech with many consecutive failures
                treatment = {
                    "strategy": "relearn",
                    "action": "Reset item and rewrite it with simplified content",
                    "reason": "Multiple consecutive failures indicate fundamental misunderstanding"
                }
            elif avg_response_time > 10000:  # 10 seconds
                # Slow recall indicates weak memory trace
                treatment = {
                    "strategy": "simplify",
                    "action": "Break this item into multiple simpler items",
                    "reason": "Long response times suggest complexity issues"
                }
            elif "recent_fail_ratio" in leech_data and leech_data["recent_fail_ratio"] > 0.6:
                # Recently becoming problematic
                treatment = {
                    "strategy": "hint",
                    "action": "Add memory aids or hints to the question",
                    "reason": "Recent failures despite earlier success"
                }
            else:
                # Default treatment
                treatment = {
                    "strategy": "mnemonic",
                    "action": "Apply a mnemonic technique or create a memorable association",
                    "reason": "General difficulties with retention"
                }
                
            treatments[item_id] = treatment
            
        return treatments
        
    def apply_leech_treatment(self, item_id, treatment_strategy):
        """
        Apply a treatment to a leech item.
        
        Args:
            item_id: ID of the learning item
            treatment_strategy: Treatment strategy to apply
            
        Returns:
            bool: Success
        """
        item = self.db_session.query(LearningItem).get(item_id)
        if not item:
            logger.warning(f"Item {item_id} not found")
            return False
            
        try:
            if treatment_strategy == "relearn":
                # Reset learning progress
                item.interval = 0
                item.repetitions = 0
                item.next_review = datetime.utcnow()
                
                # Add a note to the question
                if not item.question.startswith("[RELEARNING] "):
                    item.question = f"[RELEARNING] {item.question}"
                    
            elif treatment_strategy == "simplify":
                # Mark as simplified
                if not item.question.startswith("[SIMPLIFIED] "):
                    item.question = f"[SIMPLIFIED] {item.question}"
                    
                # Adjust difficulty
                if hasattr(item, "difficulty"):
                    item.difficulty = max(0, item.difficulty - 0.2)
                    
            elif treatment_strategy == "hint":
                # Only add hint marker (actual hint should be added manually)
                if not item.question.startswith("[HINT] "):
                    item.question = f"[HINT] {item.question}"
                    
            elif treatment_strategy == "mnemonic":
                # Only add mnemonic marker (actual mnemonic should be added manually)
                if not item.question.startswith("[MNEMONIC] "):
                    item.question = f"[MNEMONIC] {item.question}"
                    
            # Reset learning parameters to give it a fresh start
            if hasattr(item, "stability"):
                item.stability = 1.0
                
            # Set a review sooner than normal
            item.next_review = datetime.utcnow() + timedelta(days=1)
            
            self.db_session.commit()
            logger.info(f"Applied {treatment_strategy} treatment to item {item_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error applying treatment to item {item_id}: {e}")
            self.db_session.rollback()
            return False 