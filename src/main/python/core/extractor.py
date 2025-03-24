# core/content_extractor/extractor.py

import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import re
from bs4 import BeautifulSoup
import nltk
from nltk.tokenize import sent_tokenize

from sqlalchemy.orm import Session
from core.knowledge_base.models import Document, Extract, LearningItem

logger = logging.getLogger(__name__)

class ContentExtractor:
    """
    Tool for extracting knowledge fragments from documents and
    creating learning items from them.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        
        # Ensure NLTK resources are downloaded
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt')
    
    def create_extract(self, 
                       document_id: int, 
                       content: str, 
                       context: Optional[str] = None, 
                       position: Optional[str] = None,
                       parent_id: Optional[int] = None,
                       priority: int = 50) -> Optional[Extract]:
        """
        Create a new extract from document content.
        
        Args:
            document_id: ID of the source document
            content: Extract content text
            context: Optional surrounding context
            position: Optional position information in the document
            parent_id: Optional parent extract ID for hierarchical extracts
            priority: Priority on a scale from 1-100 (default: 50)
            
        Returns:
            Extract object if creation successful, None otherwise
        """
        try:
            # Validate document exists
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document not found: {document_id}")
                return None
            
            # Validate parent extract if specified
            if parent_id:
                parent = self.db_session.query(Extract).get(parent_id)
                if not parent:
                    logger.error(f"Parent extract not found: {parent_id}")
                    return None
                
                # If parent is for a different document, reject
                if parent.document_id != document_id:
                    logger.error(f"Parent extract belongs to a different document")
                    return None
            
            # Create extract
            extract = Extract(
                content=content,
                context=context,
                document_id=document_id,
                parent_id=parent_id,
                position=position,
                priority=priority,
                created_date=datetime.utcnow()
            )
            
            # Add to database
            self.db_session.add(extract)
            self.db_session.commit()
            
            logger.info(f"Extract created: {extract.id}")
            return extract
            
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            self.db_session.rollback()
            return None
    
    def auto_segment_content(self, document_id: int) -> List[Dict[str, Any]]:
        """
        Automatically segment document content into potential extracts.
        
        Args:
            document_id: ID of the document
            
        Returns:
            List of dictionaries with potential extract information
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return []
        
        segments = []
        
        try:
            # Different handling based on content type
            if document.content_type == 'pdf':
                segments = self._segment_pdf(document)
            elif document.content_type in ['html', 'htm']:
                segments = self._segment_html(document)
            elif document.content_type in ['txt', 'md']:
                segments = self._segment_text(document)
            else:
                logger.warning(f"No auto-segmentation for content type: {document.content_type}")
            
            return segments
            
        except Exception as e:
            logger.exception(f"Error segmenting document: {e}")
            return []
    
    def _segment_pdf(self, document: Document) -> List[Dict[str, Any]]:
        """Segment a PDF document into potential extracts."""
        # This would be more complex in a real implementation
        # using the PDF content structure
        
        # For now, just demonstrate the concept with basic segmentation
        import PyPDF2
        segments = []
        
        try:
            with open(document.file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                
                for page_num, page in enumerate(reader.pages):
                    text = page.extract_text()
                    
                    # Split into paragraphs
                    paragraphs = [p for p in text.split('\n\n') if p.strip()]
                    
                    for i, paragraph in enumerate(paragraphs):
                        # Create segment for each substantial paragraph
                        if len(paragraph.split()) >= 5:  # At least 5 words
                            segments.append({
                                'content': paragraph,
                                'position': f"page:{page_num+1},para:{i+1}",
                                'priority': 50  # Default priority
                            })
        except Exception as e:
            logger.exception(f"Error segmenting PDF: {e}")
        
        return segments
    
    def _segment_html(self, document: Document) -> List[Dict[str, Any]]:
        """Segment an HTML document into potential extracts."""
        segments = []
        
        try:
            with open(document.file_path, 'r', encoding='utf-8') as file:
                html_content = file.read()
            
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract segments from headings and paragraphs
            headings = soup.find_all(['h1', 'h2', 'h3'])
            paragraphs = soup.find_all('p')
            
            # Process headings
            for i, heading in enumerate(headings):
                if heading.text.strip():
                    tag_name = heading.name  # e.g., 'h1', 'h2', etc.
                    # Higher priority for higher-level headings
                    priority = 80 - (int(tag_name[1]) * 10)
                    
                    segments.append({
                        'content': heading.text.strip(),
                        'position': f"heading:{i+1},{tag_name}",
                        'priority': priority
                    })
            
            # Process paragraphs
            for i, para in enumerate(paragraphs):
                if para.text.strip() and len(para.text.strip().split()) >= 5:
                    segments.append({
                        'content': para.text.strip(),
                        'position': f"para:{i+1}",
                        'priority': 50
                    })
        
        except Exception as e:
            logger.exception(f"Error segmenting HTML: {e}")
        
        return segments
    
    def _segment_text(self, document: Document) -> List[Dict[str, Any]]:
        """Segment a text document into potential extracts."""
        segments = []
        
        try:
            with open(document.file_path, 'r', encoding='utf-8') as file:
                text_content = file.read()
            
            # Split into paragraphs
            paragraphs = [p for p in text_content.split('\n\n') if p.strip()]
            
            for i, paragraph in enumerate(paragraphs):
                if len(paragraph.split()) >= 5:  # At least 5 words
                    # Check if it looks like a heading
                    is_heading = False
                    lines = paragraph.split('\n')
                    if len(lines) == 1 and len(lines[0]) <= 100 and not lines[0].endswith('.'):
                        is_heading = True
                    
                    priority = 70 if is_heading else 50
                    
                    segments.append({
                        'content': paragraph,
                        'position': f"para:{i+1}",
                        'priority': priority
                    })
                
        except Exception as e:
            logger.exception(f"Error segmenting text: {e}")
        
        return segments
    
    def generate_learning_items(self, extract_id: int, 
                               item_types: List[str] = ['qa', 'cloze']) -> List[LearningItem]:
        """
        Generate learning items from an extract.
        
        Args:
            extract_id: ID of the extract
            item_types: Types of items to generate ('qa', 'cloze')
            
        Returns:
            List of generated learning items
        """
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            logger.error(f"Extract not found: {extract_id}")
            return []
        
        learning_items = []
        
        try:
            # Generate different types of learning items
            if 'qa' in item_types:
                qa_items = self._generate_qa_items(extract)
                learning_items.extend(qa_items)
            
            if 'cloze' in item_types:
                cloze_items = self._generate_cloze_items(extract)
                learning_items.extend(cloze_items)
            
            # Mark extract as processed
            extract.processed = True
            self.db_session.commit()
            
            return learning_items
            
        except Exception as e:
            logger.exception(f"Error generating learning items: {e}")
            self.db_session.rollback()
            return []
    
    def _generate_qa_items(self, extract: Extract) -> List[LearningItem]:
        """Generate question-answer items from an extract."""
        # This is a simplified implementation
        # In a real system, this would use NLP techniques to generate better questions
        
        items = []
        content = extract.content
        
        # Basic approach: use the first sentence as context and generate questions
        sentences = sent_tokenize(content)
        
        if len(sentences) >= 2:
            # Use first sentence as context and generate Q&A from subsequent sentences
            context = sentences[0]
            
            for i, sentence in enumerate(sentences[1:], 1):
                # Very simple Q&A generation - in real implementation, this would be more sophisticated
                words = sentence.split()
                if len(words) < 3:
                    continue
                
                # Extract key information
                key_info = self._extract_key_information(sentence)
                if key_info:
                    for key, info in key_info.items():
                        question = sentence.replace(info, "________")
                        question = f"What {key} is mentioned in this sentence: {question}"
                        
                        # Create learning item
                        item = LearningItem(
                            extract_id=extract.id,
                            item_type='qa',
                            question=question,
                            answer=info,
                            priority=extract.priority,
                            created_date=datetime.utcnow()
                        )
                        
                        self.db_session.add(item)
                        items.append(item)
        
        self.db_session.commit()
        return items
    
    def _generate_cloze_items(self, extract: Extract) -> List[LearningItem]:
        """Generate cloze deletion items from an extract."""
        items = []
        content = extract.content
        
        # Split into sentences
        sentences = sent_tokenize(content)
        
        for sentence in sentences:
            words = sentence.split()
            if len(words) < 5:  # Skip very short sentences
                continue
            
            # Create cloze deletions for key terms
            key_terms = self._identify_key_terms(sentence)
            
            for term in key_terms:
                # Create cloze deletion
                cloze_question = sentence.replace(term, "[...]")
                
                # Create learning item
                item = LearningItem(
                    extract_id=extract.id,
                    item_type='cloze',
                    question=cloze_question,
                    answer=term,
                    priority=extract.priority,
                    created_date=datetime.utcnow()
                )
                
                self.db_session.add(item)
                items.append(item)
        
        self.db_session.commit()
        return items
    
    def _extract_key_information(self, sentence: str) -> Dict[str, str]:
        """
        Extract key information from a sentence.
        Returns a dictionary mapping information type to the extracted info.
        """
        info = {}
        
        # This is a very basic implementation
        # In a real system, this would use NLP techniques
        
        # Look for dates
        date_pattern = r'\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{1,2}-\d{1,2}\b'
        dates = re.findall(date_pattern, sentence)
        if dates:
            info['date'] = dates[0]
        
        # Look for numbers
        number_pattern = r'\b\d+\b'
        numbers = re.findall(number_pattern, sentence)
        if numbers:
            info['number'] = numbers[0]
        
        # Look for proper nouns (simplified approach)
        # In a real implementation, we'd use NER (Named Entity Recognition)
        proper_noun_pattern = r'\b[A-Z][a-z]+\b'
        proper_nouns = re.findall(proper_noun_pattern, sentence)
        if proper_nouns and len(proper_nouns[0]) > 3:
            info['entity'] = proper_nouns[0]
        
        return info
    
    def _identify_key_terms(self, sentence: str) -> List[str]:
        """Identify key terms in a sentence for cloze deletions."""
        key_terms = []
        
        # This is a simplified implementation
        # In a real system, this would use NLP techniques
        
        words = sentence.split()
        
        # Look for longer words (potential key terms)
        for word in words:
            # Clean word of punctuation
            clean_word = word.strip('.,;:?!()"\'')
            
            # Check if it's a substantive word (not a stopword, longer than 5 chars)
            if len(clean_word) > 5 and clean_word.lower() not in ['should', 'would', 'could', 'about', 'there', 'their', 'these', 'those']:
                key_terms.append(word)
        
        # Limit to a few terms
        return key_terms[:2]  # At most 2 cloze deletions per sentence


# ui/extract_view.py - UI component for working with extracts

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QPushButton, QSlider, QComboBox, QListWidget, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot

from core.knowledge_base.models import Extract, Document, LearningItem
from core.content_extractor.extractor import ContentExtractor

class ExtractView(QWidget):
    """UI component for viewing and editing extracts."""
    
    closed = pyqtSignal()
    
    def __init__(self, extract: Extract, db_session):
        super().__init__()
        
        self.extract = extract
        self.db_session = db_session
        self.extractor = ContentExtractor(db_session)
        
        # Set up UI
        self._create_ui()
        self._load_extract()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Extract info
        info_layout = QHBoxLayout()
        self.title_label = QLabel("Extract")
        info_layout.addWidget(self.title_label)
        info_layout.addStretch()
        
        # Priority slider
        info_layout.addWidget(QLabel("Priority:"))
        self.priority_slider = QSlider(Qt.Orientation.Horizontal)
        self.priority_slider.setMinimum(1)
        self.priority_slider.setMaximum(100)
        self.priority_slider.setTickInterval(10)
        self.priority_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.priority_slider.valueChanged.connect(self._on_priority_changed)
        info_layout.addWidget(self.priority_slider)
        
        main_layout.addLayout(info_layout)
        
        # Content splitter
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Extract content
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.addWidget(QLabel("Content:"))
        self.content_edit = QTextEdit()
        content_layout.addWidget(self.content_edit)
        
        # Save button
        save_layout = QHBoxLayout()
        save_layout.addStretch()
        self.save_button = QPushButton("Save Changes")
        self.save_button.clicked.connect(self._on_save)
        save_layout.addWidget(self.save_button)
        content_layout.addLayout(save_layout)
        
        # Learning items
        items_widget = QWidget()
        items_layout = QVBoxLayout(items_widget)
        items_layout.addWidget(QLabel("Learning Items:"))
        
        # Learning item list
        self.item_list = QListWidget()
        items_layout.addWidget(self.item_list)
        
        # Item generation controls
        gen_layout = QHBoxLayout()
        gen_layout.addWidget(QLabel("Generate:"))
        
        self.type_combo = QComboBox()
        self.type_combo.addItem("Question-Answer", "qa")
        self.type_combo.addItem("Cloze Deletion", "cloze")
        self.type_combo.addItem("Both", "both")
        gen_layout.addWidget(self.type_combo)
        
        self.generate_button = QPushButton("Generate Items")
        self.generate_button.clicked.connect(self._on_generate_items)
        gen_layout.addWidget(self.generate_button)
        
        items_layout.addLayout(gen_layout)
        
        # Add widgets to splitter
        splitter.addWidget(content_widget)
        splitter.addWidget(items_widget)
        
        main_layout.addWidget(splitter)
    
    def _load_extract(self):
        """Load extract data into the UI."""
        # Load extract metadata
        document = self.db_session.query(Document).get(self.extract.document_id)
        if document:
            self.title_label.setText(f"Extract from: {document.title}")
        
        # Set priority slider
        self.priority_slider.setValue(self.extract.priority)
        
        # Set content
        self.content_edit.setText(self.extract.content)
        
        # Load learning items
        self._load_learning_items()
    
    def _load_learning_items(self):
        """Load learning items associated with this extract."""
        self.item_list.clear()
        
        items = self.db_session.query(LearningItem).filter(
            LearningItem.extract_id == self.extract.id
        ).all()
        
        for item in items:
            # Display differently based on item type
            if item.item_type == 'qa':
                self.item_list.addItem(f"Q&A: {item.question[:50]}...")
            elif item.item_type == 'cloze':
                self.item_list.addItem(f"Cloze: {item.question[:50]}...")
            else:
                self.item_list.addItem(f"{item.item_type}: {item.question[:50]}...")
    
    @pyqtSlot()
    def _on_save(self):
        """Save changes to the extract."""
        # Update content
        self.extract.content = self.content_edit.toPlainText()
        
        # Save to database
        self.db_session.commit()
    
    @pyqtSlot(int)
    def _on_priority_changed(self, value):
        """Update extract priority."""
        self.extract.priority = value
        self.db_session.commit()
    
    @pyqtSlot()
    def _on_generate_items(self):
        """Generate learning items from the extract."""
        item_type = self.type_combo.currentData()
        
        if item_type == "both":
            types = ["qa", "cloze"]
        else:
            types = [item_type]
        
        # Generate items
        items = self.extractor.generate_learning_items(self.extract.id, types)
        
        # Refresh the list
        self._load_learning_items()
