# core/spaced_repetition/queue_manager.py

import logging
import math
from typing import Dict, Any, List, Tuple, Optional, Union
from datetime import datetime, timedelta
import random

from sqlalchemy import func, or_, and_, desc, asc
from sqlalchemy.orm import Session, aliased
from core.knowledge_base.models import Document, Category, Extract, LearningItem, Tag

logger = logging.getLogger(__name__)

class QueueManager:
    """
    Manager for document reading queue, implementing FSRS-inspired scheduling.
    
    This class handles the scheduling of documents for incremental reading
    using principles from the Free Spaced Repetition Scheduler (FSRS) algorithm.
    """
    
    # Constants for the algorithm
    STABILITY_SCALAR = 0.9  # Controls how stability grows with each review
    RETRIEVABILITY_THRESHOLD = 0.7  # Target retention rate (70%)
    DIFFICULTY_WEIGHT = 1.0  # Initial weight for difficulty
    PRIORITY_WEIGHT = 2.0  # Weight for priority in scheduling decisions
    RANDOMNESS_FACTOR = 0.0  # Default randomness (0.0 = deterministic, 1.0 = fully random)
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.randomness_factor = self.RANDOMNESS_FACTOR  # Default randomness setting
    
    def set_randomness(self, factor: float):
        """
        Set the randomness factor for queue selection.
        
        Args:
            factor: A float between 0.0 (deterministic) and 1.0 (fully random)
        """
        self.randomness_factor = max(0.0, min(1.0, factor))
        
    def get_randomness(self) -> float:
        """
        Get the current randomness factor.
        
        Returns:
            The current randomness factor (0.0-1.0)
        """
        return self.randomness_factor

    def get_next_document(self, 
                          count: int = 1, 
                          category_id: Optional[int] = None, 
                          tags: List[str] = None) -> List[Document]:
        """
        Get the next document(s) to read from the queue.
        
        Args:
            count: Number of documents to retrieve
            category_id: Optional category filter
            tags: Optional list of tags to filter by
            
        Returns:
            List of Document objects to read next
        """
        # Query all documents
        query = self.db_session.query(Document)
        
        # Apply filters
        if category_id is not None:
            query = query.filter(Document.category_id == category_id)
        
        if tags:
            for tag in tags:
                query = query.filter(Document.tags.any(Tag.name.ilike(f"%{tag}%")))
        
        # If randomness factor is high, use more randomness in selection
        if self.randomness_factor > 0.8:
            # Highly random - select almost randomly with small weight for priority
            return self._select_with_high_randomness(query, count)
        elif self.randomness_factor > 0.5:
            # Medium randomness - mix of due documents and random selections
            return self._select_with_medium_randomness(query, count)
        elif self.randomness_factor > 0.0:
            # Low randomness - mostly due documents with some randomness
            return self._select_with_low_randomness(query, count)
        else:
            # No randomness - use standard algorithm
            return self._select_deterministic(query, count)
    
    def _select_deterministic(self, query, count: int) -> List[Document]:
        """Standard deterministic document selection."""
        # Get due documents first (those with next_reading date in the past)
        due_docs = query.filter(
            Document.next_reading_date <= datetime.utcnow()
        ).order_by(
            Document.priority.desc(),  # Higher priority first
            Document.next_reading_date  # Earlier due date first
        ).limit(count).all()
        
        # If we have enough due documents, return them
        if len(due_docs) >= count:
            return due_docs
        
        # Otherwise, get additional documents to make up the count
        remaining_count = count - len(due_docs)
        
        # Get new documents (those never read before)
        new_docs = query.filter(
            Document.next_reading_date == None
        ).order_by(
            Document.priority.desc(),  # Higher priority first
            Document.imported_date.desc()  # Recently imported first
        ).limit(remaining_count).all()
        
        # Combine and return
        return due_docs + new_docs
    
    def _select_with_low_randomness(self, query, count: int) -> List[Document]:
        """Select documents with a small random factor."""
        # Get more documents than requested so we can add randomness
        pool_size = count * 2
        
        # Get due documents
        due_docs = query.filter(
            Document.next_reading_date <= datetime.utcnow()
        ).order_by(
            Document.priority.desc(),
            Document.next_reading_date
        ).limit(pool_size).all()
        
        # Get new documents
        new_docs = query.filter(
            Document.next_reading_date == None
        ).order_by(
            Document.priority.desc(),
            Document.imported_date.desc()
        ).limit(pool_size).all()
        
        # Create pool of documents
        pool = due_docs + new_docs
        
        # If pool is smaller than count, add more documents
        if len(pool) < count:
            # Add some documents with future due dates
            future_docs = query.filter(
                Document.next_reading_date > datetime.utcnow()
            ).order_by(
                Document.next_reading_date
            ).limit(count - len(pool)).all()
            
            pool.extend(future_docs)
        
        # If we still don't have enough, return what we have
        if len(pool) <= count:
            return pool
        
        # Add some randomness - select a mix of documents with bias toward higher priority
        result = []
        
        # First, ensure we include at least some due documents (if available)
        due_count = min(len(due_docs), count // 2)
        if due_count > 0:
            result.extend(due_docs[:due_count])
        
        # Fill remaining slots with weighted random selection
        remaining = count - len(result)
        if remaining > 0 and len(pool) > len(result):
            remaining_pool = [doc for doc in pool if doc not in result]
            
            # Weight by priority and randomness factor
            weights = []
            for doc in remaining_pool:
                # Base weight on priority (1-100)
                weight = doc.priority
                
                # Add randomness
                random_component = random.random() * 50 * self.randomness_factor
                weight = weight * (1 - self.randomness_factor) + random_component
                
                weights.append(weight)
            
            # Normalize weights
            total_weight = sum(weights)
            if total_weight > 0:
                weights = [w / total_weight for w in weights]
            else:
                weights = [1.0 / len(weights)] * len(weights)
            
            # Select remaining documents
            selected_indices = random.choices(
                range(len(remaining_pool)), 
                weights=weights, 
                k=remaining
            )
            
            for idx in selected_indices:
                result.append(remaining_pool[idx])
        
        return result
    
    def _select_with_medium_randomness(self, query, count: int) -> List[Document]:
        """Select documents with medium randomness."""
        # Get a larger pool of documents
        pool_size = count * 3
        
        # Get a diverse pool of documents
        pool = []
        
        # Add some due documents
        due_docs = query.filter(
            Document.next_reading_date <= datetime.utcnow()
        ).order_by(
            Document.priority.desc()
        ).limit(pool_size // 3).all()
        pool.extend(due_docs)
        
        # Add some new documents
        new_docs = query.filter(
            Document.next_reading_date == None
        ).order_by(
            Document.imported_date.desc()
        ).limit(pool_size // 3).all()
        pool.extend(new_docs)
        
        # Add some random documents from entire collection
        random_docs = query.order_by(func.random()).limit(pool_size // 3).all()
        pool.extend(random_docs)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_pool = []
        for doc in pool:
            if doc.id not in seen:
                seen.add(doc.id)
                unique_pool.append(doc)
        
        # If we don't have enough documents, return what we have
        if len(unique_pool) <= count:
            return unique_pool
        
        # Select documents with weighted random selection
        weights = []
        for doc in unique_pool:
            # Calculate a score that combines priority and serendipity
            priority_component = doc.priority * (1 - self.randomness_factor)
            random_component = random.random() * 100 * self.randomness_factor
            
            # Give some boost to documents that:
            # - Are recently imported
            # - Have not been read before
            # - Are related to recently viewed documents
            boost = 0
            if doc.next_reading_date is None:
                boost += 20 * self.randomness_factor  # Boost for new documents
            
            if doc.imported_date and (datetime.utcnow() - doc.imported_date).days < 7:
                boost += 15 * self.randomness_factor  # Boost for recently imported
            
            # Combine all factors
            weight = priority_component + random_component + boost
            weights.append(weight)
        
        # Normalize weights
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]
        else:
            weights = [1.0 / len(weights)] * len(weights)
        
        # Select documents
        selected_indices = random.choices(
            range(len(unique_pool)), 
            weights=weights, 
            k=count
        )
        
        return [unique_pool[idx] for idx in selected_indices]
    
    def _select_with_high_randomness(self, query, count: int) -> List[Document]:
        """Select documents with high randomness, focused on serendipity and discovery."""
        # For high randomness, we want to introduce documents that might be:
        # - From categories not recently visited
        # - With diverse topics
        # - Both new and old items
        # - With varying difficulty levels
        
        # First, get a random selection of documents
        random_pool = query.order_by(func.random()).limit(count * 2).all()
        
        # Get some documents from underrepresented categories
        # This query gets documents from categories with fewer readings
        category_diversity_pool = []
        try:
            # Get documents from categories with fewer readings
            category_query = self.db_session.query(
                Document.category_id, 
                func.count(Document.id).label('doc_count')
            ).group_by(Document.category_id).order_by('doc_count').all()
            
            # Get a few documents from least-read categories
            for category_id, _ in category_query[:5]:  # Get from 5 least-read categories
                category_docs = query.filter(
                    Document.category_id == category_id
                ).order_by(func.random()).limit(2).all()
                
                category_diversity_pool.extend(category_docs)
        except Exception as e:
            logger.error(f"Error getting diverse categories: {e}")
        
        # Get some documents that haven't been read in a long time
        old_docs = query.filter(
            Document.last_reading_date != None
        ).order_by(
            Document.last_reading_date.asc()  # Oldest first
        ).limit(count // 2).all()
        
        # Combine all pools, removing duplicates
        combined_pool = []
        seen_ids = set()
        
        # Add documents from each pool, avoiding duplicates
        for doc in random_pool + category_diversity_pool + old_docs:
            if doc.id not in seen_ids:
                combined_pool.append(doc)
                seen_ids.add(doc.id)
        
        # If we don't have enough documents, return what we have
        if len(combined_pool) <= count:
            return combined_pool
        
        # For high randomness, we still keep a slight priority weighting
        weights = []
        for doc in combined_pool:
            # Base weight is mostly random with small priority component
            priority_component = doc.priority * 0.2  # Small priority influence
            random_component = random.random() * 100 * 0.8  # High randomness
            
            weight = priority_component + random_component
            weights.append(weight)
        
        # Normalize weights
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]
        else:
            weights = [1.0 / len(weights)] * len(weights)
        
        # Select documents
        selected_indices = random.choices(
            range(len(combined_pool)), 
            weights=weights, 
            k=count
        )
        
        return [combined_pool[idx] for idx in selected_indices]
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the document queue.
        
        Returns:
            Dictionary with queue statistics
        """
        stats = {}
        
        # Count total documents
        stats['total_documents'] = self.db_session.query(func.count(Document.id)).scalar() or 0
        
        # Count documents due today
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        stats['due_today'] = self.db_session.query(func.count(Document.id)).filter(
            Document.next_reading_date.between(today_start, today_end)
        ).scalar() or 0
        
        # Count documents due in the next 7 days
        next_week = today_start + timedelta(days=7)
        
        stats['due_this_week'] = self.db_session.query(func.count(Document.id)).filter(
            Document.next_reading_date.between(today_start, next_week)
        ).scalar() or 0
        
        # Count new documents (never read)
        stats['new_documents'] = self.db_session.query(func.count(Document.id)).filter(
            Document.next_reading_date == None
        ).scalar() or 0
        
        # Count overdue documents (due date in the past)
        stats['overdue'] = self.db_session.query(func.count(Document.id)).filter(
            Document.next_reading_date < today_start
        ).scalar() or 0
        
        return stats
    
    def schedule_document(self, document_id: int, rating: int) -> Dict[str, Any]:
        """
        Schedule a document for future reading based on user rating.
        
        Uses an FSRS-inspired algorithm to calculate the next reading date.
        
        Args:
            document_id: ID of the document to schedule
            rating: User rating of the document (1-5 scale)
                1: Hard/Forgot
                2: Medium/Difficult
                3: Good
                4: Easy
                5: Very Easy
                
        Returns:
            Dictionary with scheduling information
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return {}
        
        # Get current time
        now = datetime.utcnow()
        
        # Initialize scheduling parameters if this is the first reading
        if document.stability is None:
            document.stability = 1.0
            document.difficulty = 5.0  # Default difficulty (1-10 scale)
            document.reading_count = 0
            document.last_reading_date = None
        
        # Update reading count
        document.reading_count += 1
        
        # Calculate actual interval (if not first reading)
        actual_interval_days = 0
        if document.last_reading_date:
            actual_interval = now - document.last_reading_date
            actual_interval_days = actual_interval.days
        
        # FSRS-inspired algorithm
        # 1. Update difficulty based on rating
        if rating == 1:  # Hard/Forgot
            difficulty_delta = 1.0
            new_stability = max(1.0, document.stability * 0.5)  # Decrease stability
        elif rating == 2:  # Medium/Difficult
            difficulty_delta = 0.5
            new_stability = max(1.0, document.stability * 0.7)  # Slightly decrease stability
        elif rating == 3:  # Good
            difficulty_delta = 0.0
            new_stability = document.stability * (1.0 + 0.1 * self.STABILITY_SCALAR)  # Increase stability
        elif rating == 4:  # Easy
            difficulty_delta = -0.5
            new_stability = document.stability * (1.0 + 0.2 * self.STABILITY_SCALAR)  # Increase stability more
        else:  # Very Easy (5)
            difficulty_delta = -1.0
            new_stability = document.stability * (1.0 + 0.4 * self.STABILITY_SCALAR)  # Increase stability significantly
        
        # Update difficulty (constrained to 1-10 scale)
        document.difficulty = max(1.0, min(10.0, document.difficulty + difficulty_delta))
        
        # 2. Update stability
        document.stability = new_stability
        
        # 3. Calculate next interval based on stability and retrievability
        # The interval is calculated to achieve the target retrievability
        # Using the retrievability formula: R = e^(-t/S) where t is time and S is stability
        # Solving for t when R = target: t = -S * ln(target)
        target_retrievability = self.RETRIEVABILITY_THRESHOLD
        
        # Calculate optimal interval in days
        optimal_interval = -document.stability * math.log(target_retrievability)
        
        # Apply difficulty adjustment
        difficulty_factor = 1.0 - ((document.difficulty - 1.0) / 9.0) * 0.3  # Map 1-10 scale to 0.7-1.0 factor
        optimal_interval *= difficulty_factor
        
        # Apply priority adjustment (higher priority = shorter interval)
        priority_factor = 1.0 - ((document.priority - 1.0) / 99.0) * 0.5  # Map 1-100 scale to 0.5-1.0 factor
        optimal_interval *= priority_factor
        
        # Add some randomness to avoid scheduling clumps (±10%)
        randomness = 1.0 + (random.random() * 0.2 - 0.1)
        optimal_interval *= randomness
        
        # Ensure minimum interval of 1 day and maximum of 365 days
        optimal_interval = max(1.0, min(365.0, optimal_interval))
        
        # Round to nearest day
        interval_days = round(optimal_interval)
        
        # Calculate next reading date
        next_reading_date = now + timedelta(days=interval_days)
        
        # Update document
        document.last_reading_date = now
        document.next_reading_date = next_reading_date
        
        # Save changes
        self.db_session.commit()
        
        # Return scheduling information
        return {
            'document_id': document.id,
            'title': document.title,
            'stability': document.stability,
            'difficulty': document.difficulty,
            'reading_count': document.reading_count,
            'next_reading_date': next_reading_date,
            'interval_days': interval_days
        }
    
    def update_document_priority(self, document_id: int, priority: int) -> bool:
        """
        Update the priority of a document.
        
        Args:
            document_id: ID of the document
            priority: New priority value (1-100 scale)
            
        Returns:
            True if successful, False otherwise
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return False
        
        # Update priority (constrained to 1-100 scale)
        document.priority = max(1, min(100, priority))
        
        # Save changes
        self.db_session.commit()
        
        return True
    
    def get_documents_by_due_date(self, 
                                days: int = 7, 
                                category_id: Optional[int] = None,
                                include_new: bool = True) -> Dict[str, List[Document]]:
        """
        Get documents grouped by due date for the next N days.
        
        Args:
            days: Number of days to look ahead
            category_id: Optional category filter
            include_new: Whether to include new (never read) documents
            
        Returns:
            Dictionary mapping date strings to lists of documents
        """
        result = {}
        
        # Start with today
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get documents for each day
        for i in range(days):
            date = today + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            
            # Query documents due on this date
            query = self.db_session.query(Document).filter(
                func.date(Document.next_reading_date) == date.date()
            )
            
            # Apply category filter if specified
            if category_id is not None:
                query = query.filter(Document.category_id == category_id)
            
            # Order by priority
            query = query.order_by(Document.priority.desc())
            
            # Execute query
            result[date_str] = query.all()
        
        # Add "New" category if requested
        if include_new:
            # Query new documents
            query = self.db_session.query(Document).filter(
                Document.next_reading_date == None
            )
            
            # Apply category filter if specified
            if category_id is not None:
                query = query.filter(Document.category_id == category_id)
            
            # Order by priority and import date
            query = query.order_by(
                Document.priority.desc(),
                Document.imported_date.desc()
            )
            
            # Execute query
            result["New"] = query.all()
        
        # Add "Overdue" category
        overdue_query = self.db_session.query(Document).filter(
            Document.next_reading_date < today
        )
        
        # Apply category filter if specified
        if category_id is not None:
            overdue_query = overdue_query.filter(Document.category_id == category_id)
        
        # Order by due date (oldest first) and priority
        overdue_query = overdue_query.order_by(
            Document.next_reading_date,
            Document.priority.desc()
        )
        
        # Execute query
        result["Overdue"] = overdue_query.all()
        
        return result
