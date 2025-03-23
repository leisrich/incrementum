# core/spaced_repetition/incremental_reading.py

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import or_, and_, desc
from sqlalchemy.orm import Session

from core.knowledge_base.models import Document, IncrementalReading, Extract, Highlight, WebHighlight, LearningItem

logger = logging.getLogger(__name__)

class IncrementalReadingManager:
    """
    SuperMemo-style incremental reading manager.
    
    This class implements the incremental reading approach pioneered by 
    SuperMemo, which enables efficient reading of multiple materials by
    breaking them into prioritized segments and spacing out the reading
    sessions over time.
    """
    
    def __init__(self, db_session: Session):
        """
        Initialize the incremental reading manager.
        
        Args:
            db_session: Database session
        """
        self.db_session = db_session
    
    def get_reading_queue(self, limit: int = 20) -> List[Tuple[Document, IncrementalReading]]:
        """
        Get documents due for incremental reading.
        
        Args:
            limit: Maximum number of documents to return
            
        Returns:
            List of (document, reading_progress) tuples
        """
        now = datetime.utcnow()
        
        # Get items due for reading (next_read_date <= now or null)
        query = self.db_session.query(Document, IncrementalReading)\
            .join(IncrementalReading, Document.id == IncrementalReading.document_id)\
            .filter(or_(
                IncrementalReading.next_read_date <= now,
                IncrementalReading.next_read_date == None
            ))\
            .filter(IncrementalReading.percent_complete < 100)\
            .order_by(desc(IncrementalReading.reading_priority))\
            .limit(limit)
            
        return query.all()
    
    def add_document_to_queue(self, document_id: int, priority: float = 50.0) -> Optional[IncrementalReading]:
        """
        Add a document to the incremental reading queue.
        
        Args:
            document_id: Document ID
            priority: Reading priority (0-100)
            
        Returns:
            IncrementalReading object if successful, None otherwise
        """
        try:
            # Check if document exists
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document not found: {document_id}")
                return None
                
            # Check if already in queue
            existing = self.db_session.query(IncrementalReading)\
                .filter(IncrementalReading.document_id == document_id)\
                .first()
                
            if existing:
                # Update priority if already exists
                existing.reading_priority = priority
                self.db_session.commit()
                return existing
                
            # Create new incremental reading entry
            reading = IncrementalReading(
                document_id=document_id,
                reading_priority=priority,
                next_read_date=datetime.utcnow()  # Due immediately
            )
            
            self.db_session.add(reading)
            self.db_session.commit()
            
            return reading
            
        except Exception as e:
            logger.exception(f"Error adding document to incremental reading queue: {e}")
            self.db_session.rollback()
            return None
    
    def record_reading_session(self, reading_id: int, position: int, grade: int, percent_complete: float) -> bool:
        """
        Record progress from a reading session.
        
        Args:
            reading_id: IncrementalReading ID
            position: Current position in document
            grade: Quality of reading (0-5 scale)
            percent_complete: Percentage of document completed (0-100)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            reading = self.db_session.query(IncrementalReading).get(reading_id)
            if not reading:
                logger.error(f"IncrementalReading not found: {reading_id}")
                return False
                
            # Update position and progress
            reading.current_position = position
            reading.percent_complete = percent_complete
            reading.last_read_date = datetime.utcnow()
            
            # Calculate next reading date
            reading.calculate_next_date(grade)
            
            self.db_session.commit()
            return True
            
        except Exception as e:
            logger.exception(f"Error recording incremental reading session: {e}")
            self.db_session.rollback()
            return False
    
    def extract_highlight_to_item(self, highlight_id: int, is_web: bool = False) -> Optional[Extract]:
        """
        Convert a highlight to an extract for learning.
        
        Args:
            highlight_id: Highlight ID
            is_web: Whether it's a web highlight
            
        Returns:
            Created Extract if successful, None otherwise
        """
        try:
            if is_web:
                highlight = self.db_session.query(WebHighlight).get(highlight_id)
                highlight_type = "web_highlight"
            else:
                highlight = self.db_session.query(Highlight).get(highlight_id)
                highlight_type = "highlight"
                
            if not highlight:
                logger.error(f"Highlight not found: {highlight_id}")
                return None
                
            # Create extract from highlight
            extract = Extract(
                document_id=highlight.document_id,
                content=highlight.content,
                context=getattr(highlight, 'context', None),
                position=getattr(highlight, 'position', None),
                priority=50,  # Default priority
                created_date=datetime.utcnow()
            )
            
            self.db_session.add(extract)
            self.db_session.commit()
            
            return extract
            
        except Exception as e:
            logger.exception(f"Error extracting highlight to item: {e}")
            self.db_session.rollback()
            return None
    
    def create_cloze_from_extract(self, extract_id: int, cloze_text: str, hint: str = "") -> Optional[LearningItem]:
        """
        Create a cloze deletion learning item from an extract.
        
        Args:
            extract_id: Extract ID
            cloze_text: Text with [...] marking the cloze deletion
            hint: Optional hint
            
        Returns:
            Created LearningItem if successful, None otherwise
        """
        try:
            extract = self.db_session.query(Extract).get(extract_id)
            if not extract:
                logger.error(f"Extract not found: {extract_id}")
                return None
                
            # Find the answer (text within [...])
            import re
            match = re.search(r'\[(.*?)\]', cloze_text)
            if not match:
                logger.error(f"No cloze deletion found in text: {cloze_text}")
                return None
                
            answer = match.group(1)
            question = cloze_text.replace(f"[{answer}]", "___")
            
            if hint:
                question += f" (Hint: {hint})"
                
            # Create learning item
            learning_item = LearningItem(
                extract_id=extract_id,
                item_type="cloze",
                question=question,
                answer=answer,
                created_date=datetime.utcnow(),
                priority=extract.priority,
                interval=0,
                repetitions=0,
                easiness=2.5
            )
            
            self.db_session.add(learning_item)
            self.db_session.commit()
            
            return learning_item
            
        except Exception as e:
            logger.exception(f"Error creating cloze from extract: {e}")
            self.db_session.rollback()
            return None
    
    def auto_extract_important_content(self, document_id: int, max_extracts: int = 5) -> List[Extract]:
        """
        Automatically extract important content from a document.
        
        Args:
            document_id: Document ID
            max_extracts: Maximum number of extracts to create
            
        Returns:
            List of created Extract objects
        """
        try:
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document not found: {document_id}")
                return []
                
            # For web documents, try to find important content
            if document.content_type in ['web', 'html', 'jina_web']:
                from core.document_processor.handlers.jina_web_handler import JinaWebHandler
                from core.utils.settings_manager import SettingsManager
                
                # Extract content
                handler = JinaWebHandler(SettingsManager())
                content = handler.extract_content(document.file_path)
                
                # Find important sections (headings and paragraphs)
                extracts = []
                
                # First, use element detection if available
                if content['elements']:
                    # Sort by importance (h1, h2, h3, p)
                    element_importance = {'h1': 4, 'h2': 3, 'h3': 2, 'p': 1}
                    sorted_elements = sorted(
                        content['elements'], 
                        key=lambda x: element_importance.get(x['type'], 0),
                        reverse=True
                    )
                    
                    # Take top elements
                    top_elements = sorted_elements[:max_extracts]
                    
                    for element in top_elements:
                        extract_content = element['content'].strip()
                        if len(extract_content) > 10:  # Minimum length
                            extract = Extract(
                                document_id=document_id,
                                content=extract_content,
                                context=element.get('html', ''),
                                position=element.get('type', ''),
                                priority=element_importance.get(element['type'], 1) * 10,
                                created_date=datetime.utcnow()
                            )
                            self.db_session.add(extract)
                            extracts.append(extract)
                
                # If no elements found, fall back to text splitting
                if not extracts and content['text']:
                    sentences = content['text'].split('.')
                    # Get longest sentences
                    longest_sentences = sorted(sentences, key=len, reverse=True)[:max_extracts]
                    
                    for sentence in longest_sentences:
                        sentence = sentence.strip() + '.'
                        if len(sentence) > 20:  # Minimum length
                            extract = Extract(
                                document_id=document_id,
                                content=sentence,
                                context=None,
                                position=None,
                                priority=50,
                                created_date=datetime.utcnow()
                            )
                            self.db_session.add(extract)
                            extracts.append(extract)
                
                self.db_session.commit()
                return extracts
            
            # For other document types, use different strategies
            # (PDF, Text, etc.) - not implemented in this example
            
            return []
            
        except Exception as e:
            logger.exception(f"Error auto-extracting content: {e}")
            self.db_session.rollback()
            return [] 