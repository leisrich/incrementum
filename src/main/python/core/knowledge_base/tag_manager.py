# core/knowledge_base/tag_manager.py

import logging
from typing import Dict, Any, List, Tuple, Optional, Set
import re
import os

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session
from core.knowledge_base.models import Document, Extract, LearningItem, Tag
from core.content_extractor.nlp_extractor import NLPExtractor
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class TagManager:
    """
    Manager for the tagging system, allowing tag assignment, suggestion,
    and tag-based searches.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.nlp_extractor = NLPExtractor(db_session)
    
    def get_all_tags(self) -> List[Tag]:
        """
        Get all tags in the system.
        
        Returns:
            List of Tag objects
        """
        return self.db_session.query(Tag).order_by(Tag.name).all()
    
    def create_tag(self, name: str) -> Optional[Tag]:
        """
        Create a new tag if it doesn't exist.
        
        Args:
            name: Name of the tag
            
        Returns:
            Tag object if created or found, None if error
        """
        try:
            # Check if tag already exists
            tag = self.db_session.query(Tag).filter(
                func.lower(Tag.name) == func.lower(name)
            ).first()
            
            if tag:
                return tag
            
            # Create new tag
            tag = Tag(name=name)
            self.db_session.add(tag)
            self.db_session.commit()
            
            return tag
            
        except Exception as e:
            logger.exception(f"Error creating tag: {e}")
            self.db_session.rollback()
            return None
    
    def get_document_tags(self, document_id: int) -> List[Tag]:
        """
        Get tags for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            List of Tag objects
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return []
        
        return document.tags
    
    def get_extract_tags(self, extract_id: int) -> List[Tag]:
        """
        Get tags for an extract.
        
        Args:
            extract_id: ID of the extract
            
        Returns:
            List of Tag objects
        """
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            logger.error(f"Extract not found: {extract_id}")
            return []
        
        return extract.tags
    
    def add_document_tag(self, document_id: int, tag_name: str) -> bool:
        """
        Add a tag to a document.
        
        Args:
            document_id: ID of the document
            tag_name: Name of the tag to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document not found: {document_id}")
                return False
            
            # Get or create tag
            tag = self.create_tag(tag_name)
            if not tag:
                return False
            
            # Check if already tagged
            if tag in document.tags:
                return True
            
            # Add tag
            document.tags.append(tag)
            self.db_session.commit()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error adding document tag: {e}")
            self.db_session.rollback()
            return False
    
    def add_extract_tag(self, extract_id: int, tag_name: str) -> bool:
        """
        Add a tag to an extract.
        
        Args:
            extract_id: ID of the extract
            tag_name: Name of the tag to add
            
        Returns:
            True if successful, False otherwise
        """
        try:
            extract = self.db_session.query(Extract).get(extract_id)
            if not extract:
                logger.error(f"Extract not found: {extract_id}")
                return False
            
            # Get or create tag
            tag = self.create_tag(tag_name)
            if not tag:
                return False
            
            # Check if already tagged
            if tag in extract.tags:
                return True
            
            # Add tag
            extract.tags.append(tag)
            self.db_session.commit()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error adding extract tag: {e}")
            self.db_session.rollback()
            return False
    
    def remove_document_tag(self, document_id: int, tag_id: int) -> bool:
        """
        Remove a tag from a document.
        
        Args:
            document_id: ID of the document
            tag_id: ID of the tag to remove
            
        Returns:
            True if successful, False otherwise
        """
        try:
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document not found: {document_id}")
                return False
            
            tag = self.db_session.query(Tag).get(tag_id)
            if not tag:
                logger.error(f"Tag not found: {tag_id}")
                return False
            
            # Remove tag
            if tag in document.tags:
                document.tags.remove(tag)
                self.db_session.commit()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error removing document tag: {e}")
            self.db_session.rollback()
            return False
    
    def remove_extract_tag(self, extract_id: int, tag_id: int) -> bool:
        """
        Remove a tag from an extract.
        
        Args:
            extract_id: ID of the extract
            tag_id: ID of the tag to remove
            
        Returns:
            True if successful, False otherwise
        """
        try:
            extract = self.db_session.query(Extract).get(extract_id)
            if not extract:
                logger.error(f"Extract not found: {extract_id}")
                return False
            
            tag = self.db_session.query(Tag).get(tag_id)
            if not tag:
                logger.error(f"Tag not found: {tag_id}")
                return False
            
            # Remove tag
            if tag in extract.tags:
                extract.tags.remove(tag)
                self.db_session.commit()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error removing extract tag: {e}")
            self.db_session.rollback()
            return False
    
    def suggest_tags_for_document(self, document_id: int, max_suggestions: int = 5) -> List[str]:
        """
        Suggest tags for a document based on its content.
        
        Args:
            document_id: ID of the document
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggested tag names
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return []
        
        # Get document content
        content = self._get_document_content(document)
        if not content:
            return []
        
        # Extract key concepts from content
        concepts = self.nlp_extractor.identify_key_concepts(content, num_concepts=max_suggestions)
        
        # Convert to tag suggestions
        suggestions = []
        
        for concept in concepts:
            # Normalize tag name
            tag_name = self._normalize_tag_name(concept['text'])
            if tag_name and len(tag_name) >= 2:
                suggestions.append(tag_name)
        
        return suggestions
    
    def suggest_tags_for_extract(self, extract_id: int, max_suggestions: int = 5) -> List[str]:
        """
        Suggest tags for an extract based on its content.
        
        Args:
            extract_id: ID of the extract
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of suggested tag names
        """
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            logger.error(f"Extract not found: {extract_id}")
            return []
        
        # Extract key concepts from content
        concepts = self.nlp_extractor.identify_key_concepts(extract.content, num_concepts=max_suggestions)
        
        # Convert to tag suggestions
        suggestions = []
        
        for concept in concepts:
            # Normalize tag name
            tag_name = self._normalize_tag_name(concept['text'])
            if tag_name and len(tag_name) >= 2:
                suggestions.append(tag_name)
        
        return suggestions
    
    def find_related_documents(self, tag_names: List[str]) -> List[Document]:
        """
        Find documents related to the given tags.
        
        Args:
            tag_names: List of tag names to search for
            
        Returns:
            List of Document objects
        """
        if not tag_names:
            return []
        
        # Build query for documents with any of the tags
        tag_filters = []
        for tag_name in tag_names:
            tag_filters.append(
                Tag.name.ilike(f"%{tag_name}%")
            )
        
        # Query documents with any of the tags
        documents = self.db_session.query(Document).join(
            Document.tags
        ).filter(
            or_(*tag_filters)
        ).distinct().all()
        
        return documents
    
    def find_related_extracts(self, tag_names: List[str]) -> List[Extract]:
        """
        Find extracts related to the given tags.
        
        Args:
            tag_names: List of tag names to search for
            
        Returns:
            List of Extract objects
        """
        if not tag_names:
            return []
        
        # Build query for extracts with any of the tags
        tag_filters = []
        for tag_name in tag_names:
            tag_filters.append(
                Tag.name.ilike(f"%{tag_name}%")
            )
        
        # Query extracts with any of the tags
        extracts = self.db_session.query(Extract).join(
            Extract.tags
        ).filter(
            or_(*tag_filters)
        ).distinct().all()
        
        return extracts
    
    def _get_document_content(self, document: Document) -> str:
        """Get the text content of a document."""
        try:
            # Check if the file exists
            if not os.path.exists(document.file_path):
                logger.error(f"Document file not found: {document.file_path}")
                return f"[File not found: {document.file_path}]"
                
            # Handle different document types
            file_extension = os.path.splitext(document.file_path)[1].lower()
            
            # Special handling for audio files
            if document.content_type in ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac']:
                # For audio files, just use minimal metadata to avoid processing huge binary data
                metadata = f"Audio file: {document.title}\nArtist: {document.author or 'Unknown'}\n"
                if hasattr(document, 'duration') and document.duration:
                    metadata += f"Duration: {document.duration} seconds\n"
                
                # Add some generic audio-related terms to improve tag suggestions
                metadata += "Keywords: audio, sound, music, podcast, listening, recording"
                return metadata
            
            if file_extension == '.pdf':
                # Process PDF
                import fitz  # PyMuPDF
                
                with fitz.open(document.file_path) as pdf:
                    text = ""
                    for page in pdf:
                        text += page.get_text()
                    return text
                
            elif file_extension in ['.html', '.htm']:
                # Process HTML
                try:
                    with open(document.file_path, 'r', encoding='utf-8') as f:
                        soup = BeautifulSoup(f.read(), 'lxml')
                        return soup.get_text(separator='\n')
                except UnicodeDecodeError:
                    pass
                
                # Fallback to latin-1 if all else fails
                with open(document.file_path, 'r', encoding='latin-1', errors='replace') as f:
                    soup = BeautifulSoup(f.read(), 'lxml')
                    return soup.get_text(separator='\n')
            
            else:  # Plain text or other formats (including EPUB)
                # Try different encodings
                for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        with open(document.file_path, 'r', encoding=encoding) as f:
                            return f.read()
                    except UnicodeDecodeError:
                        continue
                
                # Fallback to latin-1 with replacement if all else fails
                with open(document.file_path, 'r', encoding='latin-1', errors='replace') as f:
                    return f.read()
                    
        except Exception as e:
            logger.exception(f"Error reading document content: {e}")
            return f"[Error reading document content: {str(e)}]"
    
    def _normalize_tag_name(self, text: str) -> str:
        """
        Normalize text for use as a tag name.
        
        Args:
            text: Text to normalize
            
        Returns:
            Normalized tag name
        """
        # Convert to lowercase
        text = text.lower()
        
        # Remove special characters except spaces and hyphens
        text = re.sub(r'[^\w\s-]', '', text)
        
        # Replace spaces with hyphens
        text = re.sub(r'\s+', '-', text)
        
        # Remove leading/trailing hyphens
        text = text.strip('-')
        
        return text


# ui/tag_view.py

import logging
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QComboBox, QGroupBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon

from core.knowledge_base.models import Document, Extract, Tag
from core.knowledge_base.tag_manager import TagManager

logger = logging.getLogger(__name__)

class TagView(QWidget):
    """Widget for managing tags for documents and extracts."""
    
    def __init__(self, db_session, item_type: str, item_id: int):
        """
        Initialize the tag view.
        
        Args:
            db_session: Database session
            item_type: Type of item ('document' or 'extract')
            item_id: ID of the item
        """
        super().__init__()
        
        self.db_session = db_session
        self.tag_manager = TagManager(db_session)
        self.item_type = item_type
        self.item_id = item_id
        
        # Load item
        self.item = None
        self._load_item()
        
        # Create UI
        self._create_ui()
        
        # Load tags
        self._load_tags()
    
    def _load_item(self):
        """Load the document or extract."""
        if self.item_type == 'document':
            self.item = self.db_session.query(Document).get(self.item_id)
        elif self.item_type == 'extract':
            self.item = self.db_session.query(Extract).get(self.item_id)
        else:
            logger.error(f"Unknown item type: {self.item_type}")
            self.item = None
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        
        if self.item_type == 'document':
            title = f"Tags for document: {self.item.title}" if self.item else "Tags"
        else:  # extract
            title = f"Tags for extract" if self.item else "Tags"
        
        header_label = QLabel(title)
        header_layout.addWidget(header_label)
        
        main_layout.addLayout(header_layout)
        
        # Current tags
        current_tags_group = QGroupBox("Current Tags")
        tags_layout = QVBoxLayout(current_tags_group)
        
        self.tags_list = QListWidget()
        tags_layout.addWidget(self.tags_list)
        
        # Tag management controls
        tag_controls_layout = QHBoxLayout()
        
        self.new_tag_input = QLineEdit()
        self.new_tag_input.setPlaceholderText("Enter new tag")
        tag_controls_layout.addWidget(self.new_tag_input)
        
        self.add_tag_button = QPushButton("Add Tag")
        self.add_tag_button.clicked.connect(self._on_add_tag)
        tag_controls_layout.addWidget(self.add_tag_button)
        
        self.remove_tag_button = QPushButton("Remove Selected")
        self.remove_tag_button.clicked.connect(self._on_remove_tag)
        self.remove_tag_button.setEnabled(False)  # Initially disabled
        tag_controls_layout.addWidget(self.remove_tag_button)
        
        tags_layout.addLayout(tag_controls_layout)
        
        main_layout.addWidget(current_tags_group)
        
        # Tag suggestions
        suggestions_group = QGroupBox("Suggested Tags")
        suggestions_layout = QVBoxLayout(suggestions_group)
        
        self.suggestions_list = QListWidget()
        self.suggestions_list.itemDoubleClicked.connect(self._on_suggestion_selected)
        suggestions_layout.addWidget(self.suggestions_list)
        
        suggestions_controls_layout = QHBoxLayout()
        
        self.suggest_button = QPushButton("Generate Suggestions")
        self.suggest_button.clicked.connect(self._on_generate_suggestions)
        suggestions_controls_layout.addWidget(self.suggest_button)
        
        suggestions_layout.addLayout(suggestions_controls_layout)
        
        main_layout.addWidget(suggestions_group)
        
        # Connect signals
        self.tags_list.itemSelectionChanged.connect(self._on_tag_selection_changed)
    
    def _load_tags(self):
        """Load current tags for the item."""
        if not self.item:
            return
        
        self.tags_list.clear()
        
        if self.item_type == 'document':
            tags = self.tag_manager.get_document_tags(self.item_id)
        else:  # extract
            tags = self.tag_manager.get_extract_tags(self.item_id)
        
        for tag in tags:
            item = QListWidgetItem(tag.name)
            item.setData(Qt.ItemDataRole.UserRole, tag.id)
            self.tags_list.addItem(item)
    
    @pyqtSlot()
    def _on_add_tag(self):
        """Add a new tag to the item."""
        if not self.item:
            return
        
        tag_name = self.new_tag_input.text().strip()
        if not tag_name:
            return
        
        success = False
        if self.item_type == 'document':
            success = self.tag_manager.add_document_tag(self.item_id, tag_name)
        else:  # extract
            success = self.tag_manager.add_extract_tag(self.item_id, tag_name)
        
        if success:
            self.new_tag_input.clear()
            self._load_tags()
        else:
            QMessageBox.warning(
                self, "Error", 
                f"Failed to add tag: {tag_name}"
            )
    
    @pyqtSlot()
    def _on_remove_tag(self):
        """Remove the selected tag from the item."""
        if not self.item:
            return
        
        selected_items = self.tags_list.selectedItems()
        if not selected_items:
            return
        
        selected_item = selected_items[0]
        tag_id = selected_item.data(Qt.ItemDataRole.UserRole)
        
        success = False
        if self.item_type == 'document':
            success = self.tag_manager.remove_document_tag(self.item_id, tag_id)
        else:  # extract
            success = self.tag_manager.remove_extract_tag(self.item_id, tag_id)
        
        if success:
            self._load_tags()
        else:
            QMessageBox.warning(
                self, "Error", 
                f"Failed to remove tag"
            )
    
    @pyqtSlot()
    def _on_generate_suggestions(self):
        """Generate tag suggestions for the item."""
        if not self.item:
            return
        
        suggestions = []
        if self.item_type == 'document':
            suggestions = self.tag_manager.suggest_tags_for_document(self.item_id)
        else:  # extract
            suggestions = self.tag_manager.suggest_tags_for_extract(self.item_id)
        
        self.suggestions_list.clear()
        
        for suggestion in suggestions:
            self.suggestions_list.addItem(suggestion)
    
    @pyqtSlot(QListWidgetItem)
    def _on_suggestion_selected(self, item):
        """Handle selection of a suggested tag."""
        tag_name = item.text()
        self.new_tag_input.setText(tag_name)
        self._on_add_tag()
    
    @pyqtSlot()
    def _on_tag_selection_changed(self):
        """Handle selection change in the tags list."""
        selected_items = self.tags_list.selectedItems()
        self.remove_tag_button.setEnabled(bool(selected_items))


# ui/tag_search_view.py

import logging
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QComboBox, QGroupBox, QTabWidget, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon

from core.knowledge_base.models import Document, Extract, Tag
from core.knowledge_base.tag_manager import TagManager

logger = logging.getLogger(__name__)

class TagSearchView(QWidget):
    """Widget for searching content by tags."""
    
    itemSelected = pyqtSignal(str, int)  # type, id
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.tag_manager = TagManager(db_session)
        
        # Create UI
        self._create_ui()
        
        # Load tags
        self._load_tags()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header
        header_label = QLabel("Search by Tags")
        main_layout.addWidget(header_label)
        
        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Tags panel
        tags_panel = QWidget()
        tags_layout = QVBoxLayout(tags_panel)
        
        # Search box
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search tags...")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_input)
        
        tags_layout.addLayout(search_layout)
        
        # Tags list
        self.tags_list = QListWidget()
        self.tags_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.tags_list.itemSelectionChanged.connect(self._on_tags_selected)
        tags_layout.addWidget(self.tags_list)
        
        # Results panel
        results_panel = QWidget()
        results_layout = QVBoxLayout(results_panel)
        
        # Results tabs
        self.results_tabs = QTabWidget()
        
        # Documents tab
        self.documents_tab = QWidget()
        documents_layout = QVBoxLayout(self.documents_tab)
        
        self.documents_list = QListWidget()
        self.documents_list.itemDoubleClicked.connect(self._on_document_selected)
        documents_layout.addWidget(self.documents_list)
        
        self.results_tabs.addTab(self.documents_tab, "Documents")
        
        # Extracts tab
        self.extracts_tab = QWidget()
        extracts_layout = QVBoxLayout(self.extracts_tab)
        
        self.extracts_list = QListWidget()
        self.extracts_list.itemDoubleClicked.connect(self._on_extract_selected)
        extracts_layout.addWidget(self.extracts_list)
        
        self.results_tabs.addTab(self.extracts_tab, "Extracts")
        
        results_layout.addWidget(self.results_tabs)
        
        # Add panels to splitter
        splitter.addWidget(tags_panel)
        splitter.addWidget(results_panel)
        splitter.setStretchFactor(0, 1)  # Tags panel
        splitter.setStretchFactor(1, 2)  # Results panel
        
        main_layout.addWidget(splitter)
    
    def _load_tags(self):
        """Load all tags into the list."""
        self.tags_list.clear()
        
        tags = self.tag_manager.get_all_tags()
        
        for tag in tags:
            item = QListWidgetItem(tag.name)
            item.setData(Qt.ItemDataRole.UserRole, tag.id)
            self.tags_list.addItem(item)
    
    @pyqtSlot(str)
    def _on_search_changed(self, text):
        """Filter tags list based on search input."""
        search_text = text.lower()
        
        for i in range(self.tags_list.count()):
            item = self.tags_list.item(i)
            if not search_text or search_text in item.text().lower():
                item.setHidden(False)
            else:
                item.setHidden(True)
    
    @pyqtSlot()
    def _on_tags_selected(self):
        """Handle tag selection change."""
        selected_items = self.tags_list.selectedItems()
        selected_tag_names = [item.text() for item in selected_items]
        
        if selected_tag_names:
            # Find related documents
            documents = self.tag_manager.find_related_documents(selected_tag_names)
            
            # Update documents list
            self.documents_list.clear()
            for doc in documents:
                item = QListWidgetItem(doc.title)
                item.setData(Qt.ItemDataRole.UserRole, doc.id)
                self.documents_list.addItem(item)
            
            # Find related extracts
            extracts = self.tag_manager.find_related_extracts(selected_tag_names)
            
            # Update extracts list
            self.extracts_list.clear()
            for extract in extracts:
                content = extract.content[:100] + "..." if len(extract.content) > 100 else extract.content
                item = QListWidgetItem(content)
                item.setData(Qt.ItemDataRole.UserRole, extract.id)
                self.extracts_list.addItem(item)
    
    @pyqtSlot(QListWidgetItem)
    def _on_document_selected(self, item):
        """Handle document selection."""
        document_id = item.data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit("document", document_id)
    
    @pyqtSlot(QListWidgetItem)
    def _on_extract_selected(self, item):
        """Handle extract selection."""
        extract_id = item.data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit("extract", extract_id)
