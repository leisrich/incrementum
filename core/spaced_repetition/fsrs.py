# core/spaced_repetition/fsrs.py

import math
import logging
import random
from typing import Dict, Any, List, Tuple, Optional, Union
from datetime import datetime, timedelta

from sqlalchemy import func, or_, and_, desc, asc
from sqlalchemy.orm import Session, object_session
from core.knowledge_base.models import Document, Category, Extract, LearningItem, ReviewLog, Tag, WebHighlight, Highlight

logger = logging.getLogger(__name__)

class FSRSAlgorithm:
    """
    Implementation of the Free Spaced Repetition Scheduler (FSRS) algorithm.
    
    This implementation is based on the FSRS 2.0 algorithm by Jarrett "Phthonus" Ye
    (https://github.com/open-spaced-repetition/fsrs4anki/), adapted for both 
    documents and learning items.
    
    References:
        - https://github.com/open-spaced-repetition/fsrs4anki/
        - https://fsrs.memcode.com/
    """
    
    # Default parameters for the FSRS algorithm
    DEFAULT_PARAMS = {
        # w vector: weights of the model
        "w": [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61],
        # D: difficulty vector for each rating
        "D": [0.7, 1.5, 2.0, 2.5],
        # THETA: scaling factor for difficulty
        "THETA": 0.75,
        # forgetting index target (retention rate)
        "R_TARGET": 0.9,
        # minimum interval
        "MIN_INTERVAL": 1,  # day
        # maximum interval
        "MAX_INTERVAL": 3650,  # 10 years
        # scaling factor for priority
        "PRIORITY_WEIGHT": 0.5,
        # Incrementum A-Factor for items
        "A_FACTOR": 1.3,
        # Incrementum forgetting curve parameters
        "SM_FORGETTING_PARAMS": {
            "interval_modifier": 1.0,
            "initial_ease": 2.5,
            "easy_bonus": 1.3,
            "hard_penalty": 0.8
        },
        # Incrementum priority parameters
        "PRIORITY_DECAY": 0.01,  # Daily priority decay for items in the queue
        "PRIORITY_BOOST_HIGHLIGHT": 5,  # Priority boost for highlighted items
        "PRIORITY_BOOST_EXTRACT": 8,  # Priority boost for extracted items
    }
    
    def __init__(self, db_session: Session, params: Dict[str, Any] = None):
        """
        Initialize the FSRS Algorithm.
        
        Args:
            db_session: Database session
            params: Optional parameters to override defaults
        """
        self.db_session = db_session
        self.params = self.DEFAULT_PARAMS.copy()
        
        # Override default parameters if provided
        if params:
            self.params.update(params)
    
    #--------------------------
    # Learning Item Processing
    #--------------------------
    
    def process_item_response(self, item_id: int, rating: int, 
                         response_time: Optional[int] = None) -> Dict[str, Any]:
        """
        Process a response to a learning item and schedule the next repetition.
        
        Args:
            item_id: ID of the learning item
            rating: Rating on a scale from 1 to 4:
                   1 - Again (Forgotten)
                   2 - Hard
                   3 - Good
                   4 - Easy
            response_time: Time taken to respond in milliseconds (optional)
            
        Returns:
            Dictionary with scheduling information
        """
        # Validate rating
        if rating < 1 or rating > 4:
            logger.error(f"Invalid rating {rating}. Must be between 1 and 4.")
            rating = max(1, min(4, rating))
        
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
            grade=rating,  # Store FSRS rating (1-4) instead of SM2 grade (0-5)
            response_time=response_time,
            scheduled_interval=item.interval,
            actual_interval=actual_interval
        )
        self.db_session.add(review_log)
        
        # Initialize state if this is the first review
        if item.stability is None:
            item.stability = 0.0
            item.difficulty = 0.0
            item.reps = 0
        
        # Update item state using FSRS algorithm
        now = datetime.utcnow()
        result = self._update_item_state(item, rating, actual_interval)
        
        # Update the item with new scheduling parameters
        item.stability = result['stability']
        item.difficulty = result['difficulty']
        item.reps = result['reps']
        item.interval = result['interval']
        item.last_reviewed = now
        item.next_review = result['next_review']
        
        # Apply Incrementum-style ease factor update
        sm_params = self.params["SM_FORGETTING_PARAMS"]
        if item.easiness is None:
            item.easiness = sm_params["initial_ease"]
        
        # Update easiness based on rating (Incrementum style)
        ease_update = 0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02)
        item.easiness = max(1.3, item.easiness + ease_update)
        
        # Commit changes
        self.db_session.commit()
        
        return result
    
    def _update_item_state(self, item: LearningItem, rating: int, 
                      actual_interval: Optional[int]) -> Dict[str, Any]:
        """
        Update the state of a learning item according to the FSRS algorithm.
        
        Args:
            item: The learning item
            rating: User rating (1-4)
            actual_interval: Days since last review (or None if first review)
            
        Returns:
            Dictionary with the updated state
        """
        w = self.params["w"]
        now = datetime.utcnow()
        
        # Extract current state (or initialize if None)
        stability = item.stability or 0.0
        difficulty = item.difficulty or 0.0
        reps = item.reps or 0
        
        # Record current state before update
        old_state = {
            'stability': stability,
            'difficulty': difficulty,
            'reps': reps
        }
        
        # Calculate retrievability if not first repetition
        retrievability = 0.0
        if actual_interval and stability > 0:
            retrievability = math.exp(-(actual_interval / stability))
        
        # Update difficulty based on rating and previous difficulty
        if reps > 0:
            difficulty = self._next_difficulty(difficulty, rating - 1)  # Convert 1-4 to 0-3 for algorithm
        else:
            # Initialize difficulty based on first-time rating
            difficulty = self.params["D"][min(3, max(0, rating - 1))]
        
        # Update stability based on difficulty, retrievability, and previous stability
        if rating == 1:  # "Again" (forgotten)
            # Failed recall: reset stability to a fraction of previous value
            stability = stability * w[15]
            reps = 0  # Reset repetition counter
        else:
            if reps == 0:  # First successful recall
                stability = w[1] * (w[0] + item.priority / 100 * self.params["PRIORITY_WEIGHT"])
            else:  # Subsequent successful recall
                stability = self._next_stability(stability, difficulty, retrievability, rating - 1)
            reps += 1
        
        # Calculate the optimal interval using retrievability formula: R = e^(-t/S)
        # Solving for t when R = target: t = -S * ln(target)
        target_retrievability = self.params["R_TARGET"]
        interval = -stability * math.log(target_retrievability)
        
        # Apply difficulty adjustment
        difficulty_factor = math.pow(difficulty, -self.params["THETA"])
        interval *= difficulty_factor
        
        # Apply priority adjustment (higher priority = shorter interval)
        priority_factor = 1.0 - ((item.priority - 1.0) / 99.0) * self.params["PRIORITY_WEIGHT"]
        interval *= priority_factor
        
        # Add some randomness to avoid scheduling clumps (±5%)
        randomness = 1.0 + (random.random() * 0.1 - 0.05)
        interval *= randomness
        
        # Ensure interval stays within bounds
        interval = max(self.params["MIN_INTERVAL"], min(self.params["MAX_INTERVAL"], interval))
        
        # Round to nearest day
        interval_days = round(interval)
        
        # Calculate next review date
        next_review = now + timedelta(days=interval_days)
        
        # Return updated state and scheduling information
        return {
            'old_state': old_state,
            'stability': stability,
            'difficulty': difficulty,
            'reps': reps,
            'retrievability': retrievability,
            'interval': interval_days,
            'next_review': next_review,
            'rating': rating
        }
    
    def _next_difficulty(self, d: float, rating: int) -> float:
        """
        Calculate the next difficulty based on current difficulty and rating.
        
        Args:
            d: Current difficulty
            rating: Rating (0-3, mapped from 1-4)
            
        Returns:
            New difficulty value
        """
        w = self.params["w"]
        next_d = d - w[6] * (rating - 1)
        return max(1.0, min(10.0, next_d))
    
    def _next_stability(self, s: float, d: float, r: float, rating: int) -> float:
        """
        Calculate the next stability based on current stability, difficulty, and retrievability.
        
        Args:
            s: Current stability
            d: Current difficulty
            r: Current retrievability 
            rating: Rating (0-3, mapped from 1-4)
            
        Returns:
            New stability value
        """
        w = self.params["w"]
        hardFactor = w[7 + rating]
        
        if rating == 2:  # 'Good' response
            return s * (1 + r * d * w[2])
        elif rating == 1:  # 'Hard' response
            return s * (1 + r * d * w[2] * hardFactor)
        elif rating == 3:  # 'Easy' response
            return s * (1 + r * d * w[2] * w[3])
        else:  # 'Again' response (should not reach here, handled separately)
            return s * 0.2  # Significant reduction in stability
    
    def get_due_items(self, limit: int = 50, 
                      category_id: Optional[int] = None, 
                      tags: List[str] = None) -> List[LearningItem]:
        """
        Get items due for review based on FSRS scheduling.
        
        Args:
            limit: Maximum number of items to return
            category_id: Optional category filter
            tags: Optional list of tags to filter by
            
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
        
        # Apply tag filter if specified
        if tags:
            for tag in tags:
                query = query.join(LearningItem.extract).join(Extract.tags).filter(
                    Tag.name.ilike(f"%{tag}%")
                )
        
        # Order items using a smart algorithm:
        # 1. Items due for review (ordered by due date)
        # 2. New items (ordered by priority)
        items = query.order_by(
            # First sort by whether item is new (NULL next_review) or due
            (LearningItem.next_review == None).desc(),
            # Then sort by priority (higher first)
            LearningItem.priority.desc(),
            # Then by next review date (earliest first)
            LearningItem.next_review.asc()
        ).limit(limit).all()
        
        return items
    
    #--------------------------
    # Document Queue Processing
    #--------------------------
    
    def schedule_document(self, document_id: int, rating: int) -> Dict[str, Any]:
        """
        Schedule a document for future reading based on user rating using FSRS.
        
        Args:
            document_id: ID of the document to schedule
            rating: User rating on a scale from 1 to 4:
                   1 - Again (Forgotten/Hard)
                   2 - Hard
                   3 - Good
                   4 - Easy
                
        Returns:
            Dictionary with scheduling information
        """
        # Validate rating
        if rating < 1 or rating > 4:
            logger.error(f"Invalid rating {rating}. Must be between 1 and 4.")
            rating = max(1, min(4, rating))
            
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return {}
        
        # Get current time
        now = datetime.utcnow()
        
        # Initialize scheduling parameters if this is the first reading
        if document.stability is None:
            document.stability = 0.0
            document.difficulty = 5.0  # Default difficulty
            document.reading_count = 0
            document.reps = 0
        
        # Calculate actual interval (if not first reading)
        actual_interval_days = 0
        if document.last_reading_date:
            actual_interval = now - document.last_reading_date
            actual_interval_days = actual_interval.days
        
        # Update reading count
        document.reading_count += 1
        
        # Calculate retrievability if not first repetition
        retrievability = 0.0
        if document.last_reading_date and document.stability > 0:
            retrievability = math.exp(-(actual_interval_days / document.stability))
        
        # Debug log
        logger.debug(f"Before calculation - document: {document.title}, " 
                    f"stability: {document.stability}, difficulty: {document.difficulty}, "
                    f"reps: {document.reps}, retrievability: {retrievability}")
        
        # Update difficulty based on rating and previous difficulty
        if document.reps > 0:
            document.difficulty = self._next_difficulty(document.difficulty, rating - 1)  # Convert 1-4 to 0-3
        else:
            # Initialize difficulty based on first-time rating
            document.difficulty = self.params["D"][min(3, max(0, rating - 1))]
        
        # Update stability based on rating
        if rating == 1:  # "Again" (forgotten)
            # Failed recall: reset stability to a fraction of previous value
            document.stability = document.stability * self.params["w"][15]
            document.reps = 0  # Reset repetition counter
        else:
            if document.reps == 0:  # First successful recall
                document.stability = self.params["w"][1] * (self.params["w"][0] + document.priority / 100 * self.params["PRIORITY_WEIGHT"])
            else:  # Subsequent successful recall
                document.stability = self._next_stability(document.stability, document.difficulty, retrievability, rating - 1)
            document.reps += 1
        
        # Calculate optimal interval using retrievability formula
        target_retrievability = self.params["R_TARGET"]
        optimal_interval = -document.stability * math.log(target_retrievability)
        
        # Apply difficulty adjustment
        difficulty_factor = math.pow(document.difficulty, -self.params["THETA"])
        optimal_interval *= difficulty_factor
        
        # Apply priority adjustment (higher priority = shorter interval)
        priority_factor = 1.0 - ((document.priority - 1.0) / 99.0) * self.params["PRIORITY_WEIGHT"]
        optimal_interval *= priority_factor
        
        # Add some randomness to avoid scheduling clumps (±5%)
        randomness = 1.0 + (random.random() * 0.1 - 0.05)
        optimal_interval *= randomness
        
        # Debug calculated interval before bounds
        logger.debug(f"Calculated interval before bounds: {optimal_interval:.2f} days")
        
        # Ensure interval stays within bounds
        optimal_interval = max(self.params["MIN_INTERVAL"], min(self.params["MAX_INTERVAL"], optimal_interval))
        
        # Round to nearest day
        interval_days = round(optimal_interval)
        
        # Calculate next reading date
        next_reading_date = now + timedelta(days=interval_days)
        
        # Debug log final calculation
        logger.debug(f"After calculation - document: {document.title}, " 
                    f"stability: {document.stability:.2f}, difficulty: {document.difficulty:.2f}, "
                    f"min_interval: {self.params['MIN_INTERVAL']}, interval_days: {interval_days}, "
                    f"next_reading_date: {next_reading_date}")
        
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
            'reps': document.reps,
            'reading_count': document.reading_count,
            'next_reading_date': next_reading_date,
            'interval_days': interval_days,
            'retrievability': retrievability,
            'rating': rating
        }
    
    def get_next_documents(self, 
                          count: int = 1, 
                          category_id: Optional[int] = None, 
                          tags: List[str] = None) -> List[Document]:
        """
        Get the next document(s) to read from the queue using FSRS scheduling.
        
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
        
        # Validate priority value
        priority = max(1, min(100, priority))
        
        # Update priority
        document.priority = priority
        
        # Commit changes
        try:
            self.db_session.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating document priority: {e}")
            self.db_session.rollback()
            return False 
    
    def detect_leeches(self, threshold: int = 5) -> List[LearningItem]:
        """
        Detect leech items (items with many failures) that need special attention.
        
        Args:
            threshold: Number of failures to consider an item a leech
            
        Returns:
            List of leech items
        """
        leech_items = []
        
        # Get all learning items
        items = self.db_session.query(LearningItem).all()
        
        for item in items:
            # Count "Again" ratings (1) in review history
            failure_count = self.db_session.query(ReviewLog)\
                .filter(ReviewLog.learning_item_id == item.id)\
                .filter(ReviewLog.grade == 1)\
                .count()
            
            if failure_count >= threshold:
                leech_items.append(item)
        
        return leech_items
    
    def get_incremental_reading_queue(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get a prioritized queue for incremental reading, combining documents and extracts.
        
        This is inspired by Incrementum's incremental reading queue, which interleaves 
        documents and extracts based on priority.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of dictionaries with item info and type
        """
        now = datetime.utcnow()
        queue = []
        
        # Get due documents
        due_docs = self.db_session.query(Document)\
            .filter(or_(Document.next_reading_date <= now, Document.next_reading_date == None))\
            .order_by(desc(Document.priority))\
            .limit(limit).all()
        
        for doc in due_docs:
            queue.append({
                'type': 'document',
                'id': doc.id,
                'title': doc.title,
                'priority': doc.priority,
                'content_type': doc.content_type
            })
        
        # Get extracts with high priority
        extracts = self.db_session.query(Extract)\
            .order_by(desc(Extract.priority))\
            .limit(limit).all()
        
        for extract in extracts:
            queue.append({
                'type': 'extract',
                'id': extract.id,
                'content': extract.content[:100] + '...' if len(extract.content) > 100 else extract.content,
                'priority': extract.priority,
                'document_id': extract.document_id
            })
        
        # Sort combined queue by priority
        queue.sort(key=lambda x: x['priority'], reverse=True)
        
        return queue[:limit]
    
    def update_priorities_based_on_activity(self):
        """
        Update priorities of documents and extracts based on user activity.
        
        This implements Incrementum-style priority decay and boosts:
        - Items lose priority over time unless interacted with
        - Highlighted content gets a priority boost
        - Extracted content gets a priority boost
        """
        now = datetime.utcnow()
        decay = self.params["PRIORITY_DECAY"]
        
        # Update document priorities
        docs = self.db_session.query(Document).all()
        for doc in docs:
            # Apply priority decay based on time since last access
            if doc.last_accessed:
                days_since_access = (now - doc.last_accessed).days
                priority_decay = days_since_access * decay
                doc.priority = max(1, doc.priority - priority_decay)
            
            # Boost priority for documents with recent highlights
            recent_highlights_count = self.db_session.query(Highlight)\
                .filter(Highlight.document_id == doc.id)\
                .filter(Highlight.created_date >= now - timedelta(days=7))\
                .count()
            
            recent_web_highlights_count = self.db_session.query(WebHighlight)\
                .filter(WebHighlight.document_id == doc.id)\
                .filter(WebHighlight.created_date >= now - timedelta(days=7))\
                .count()
            
            highlight_boost = (recent_highlights_count + recent_web_highlights_count) * self.params["PRIORITY_BOOST_HIGHLIGHT"]
            doc.priority = min(100, doc.priority + highlight_boost)
            
            # Boost priority for documents with recent extracts
            recent_extracts_count = self.db_session.query(Extract)\
                .filter(Extract.document_id == doc.id)\
                .filter(Extract.created_date >= now - timedelta(days=7))\
                .count()
            
            extract_boost = recent_extracts_count * self.params["PRIORITY_BOOST_EXTRACT"]
            doc.priority = min(100, doc.priority + extract_boost)
        
        # Commit changes
        self.db_session.commit()
        
        logger.info("Updated priorities based on user activity") 

    def _ensure_document_exists(self):
        """Ensure document exists for the current web page."""
        if not self.current_url or self.current_url == "about:blank":
            logger.warning("Cannot create document: No valid URL")
            return
        
        # Check if the document already exists for this URL
        document = self.db_session.query(Document).filter(Document.source_url == self.current_url).first()
        
        if not document:
            # Create a new document
            logger.info(f"Created document for web page: {self.current_url}")
            document = Document(
                title=self.current_title,
                source_url=self.current_url,
                import_date=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                source_type="web",
            )
            self.db_session.add(document)
            self.db_session.commit()
        
        self.document_id = document.id 
