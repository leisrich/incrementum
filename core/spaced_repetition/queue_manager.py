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
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
    
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
