from core.spaced_repetition.queue_manager import QueueManager
import random
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
# Assuming your Document model is accessible, adjust import if needed
# from models.document import Document # Example import path

class FSRSAlgorithm(QueueManager):
    """
    Implementation of the Free Spaced Repetition Scheduler algorithm.
    
    This algorithm optimizes the scheduling of documents and learning items
    based on difficulty, stability, priority, and expected retrievability.
    It inherits from the QueueManager base class.
    """
    
    def __init__(self, db_session, params=None):
        """
        Initialize the FSRS algorithm with database session.
        
        Args:
            db_session: SQLAlchemy database session
            params: Optional dictionary of algorithm parameters to override defaults
        """
        # Initialize parent QueueManager
        super().__init__(db_session)
        
        # If the inherited randomness_factor isn't accessible, set it again here
        self.randomness_factor = self.RANDOMNESS_FACTOR
        
        # ... rest of initialization ... 

    def sort_queue(self, documents: List[Document], randomness_factor: float) -> List[Document]:
        """
        Sorts the document queue based on due date, priority, and randomness.

        Args:
            documents: A list of Document objects to sort.
            randomness_factor: A float between 0.0 (no randomness) and 1.0 (full randomness).

        Returns:
            A sorted list of Document objects.
        """
        if not documents:
            return []

        today = datetime.now().date() # Use date object for comparisons
        scores = []

        # Define score ranges/weights (adjust these as needed)
        MAX_SCORE = 1000.0
        OVERDUE_BASE = 900.0
        DUE_TODAY_BASE = 800.0
        DUE_SOON_BASE = 700.0 # Within 7 days
        NEW_ITEM_BASE = 500.0
        DUE_LATER_BASE = 100.0
        PRIORITY_WEIGHT = 0.5 # How much user priority affects the score (0 to 1)

        for doc in documents:
            base_score = 0.0

            if doc.next_reading_date:
                doc_due_date = doc.next_reading_date.date()
                days_diff = (doc_due_date - today).days

                if days_diff < 0:
                    # Overdue: Higher score for more overdue items
                    base_score = OVERDUE_BASE + abs(days_diff)
                elif days_diff == 0:
                    # Due Today
                    base_score = DUE_TODAY_BASE
                elif 0 < days_diff <= 7:
                    # Due Soon (within a week): Higher score for closer items
                    base_score = DUE_SOON_BASE + (7 - days_diff)
                else:
                    # Due Later
                    base_score = DUE_LATER_BASE - days_diff # Lower score for further away items
            else:
                # New Item
                base_score = NEW_ITEM_BASE

            # Add user priority component
            priority_score = (doc.priority or 0) * PRIORITY_WEIGHT
            base_score += priority_score

            # Apply randomness
            # Scale random component to be comparable to base score range
            random_component = random.random() * MAX_SCORE
            final_score = base_score * (1.0 - randomness_factor) + random_component * randomness_factor

            scores.append((final_score, doc))

        # Sort documents by the final score in descending order (highest score first)
        scores.sort(key=lambda x: x[0], reverse=True)

        # Return just the sorted documents
        sorted_documents = [doc for score, doc in scores]
        return sorted_documents 