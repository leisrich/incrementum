import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QDialog, QListWidget, QListWidgetItem, QSplitter, QMenu,
    QMessageBox, QSlider, QComboBox, QInputDialog, QLineEdit, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QObject
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter, QFont, QAction

logger = logging.getLogger(__name__)

class ReadLaterItem:
    """Class representing a Read Later bookmark item."""
    
    def __init__(self, document_id, position, created_date=None, note=None, expiry_days=None):
        self.document_id = document_id
        self.position = position
        self.created_date = created_date or datetime.utcnow()
        self.note = note
        self.expiry_date = None
        
        if expiry_days:
            self.expiry_date = self.created_date + timedelta(days=expiry_days)
    
    def is_expired(self):
        """Check if bookmark has expired."""
        if self.expiry_date:
            return datetime.utcnow() > self.expiry_date
        return False
    
    def to_dict(self):
        """Convert to dictionary for storage."""
        return {
            'document_id': self.document_id,
            'position': self.position,
            'created_date': self.created_date.isoformat(),
            'note': self.note,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create from dictionary data."""
        item = cls(
            document_id=data['document_id'],
            position=data['position'],
            note=data.get('note')
        )
        
        if 'created_date' in data:
            item.created_date = datetime.fromisoformat(data['created_date'])
            
        if 'expiry_date' in data and data['expiry_date']:
            item.expiry_date = datetime.fromisoformat(data['expiry_date'])
            
        return item

class ReadLaterManager:
    """Manager for Read Later bookmarks."""
    
    def __init__(self, db_session):
        """Initialize with database session."""
        self.db_session = db_session
        self.read_later_items = []
        self.storage_file = os.path.join(
            os.path.expanduser('~'), 
            '.incrementum', 
            'read_later_items.json'
        )
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
        
        # Load existing items
        self.load_items()
    
    def add_item(self, document_id, position, note=None, expiry_days=None):
        """Add a new Read Later item."""
        # Check for duplicates
        for item in self.read_later_items:
            if item.document_id == document_id and abs(item.position - position) < 100:
                # Update existing item instead of creating new one
                item.position = position
                item.created_date = datetime.utcnow()
                item.note = note or item.note
                
                if expiry_days:
                    item.expiry_date = item.created_date + timedelta(days=expiry_days)
                
                self.save_items()
                return item
        
        # Create new item
        item = ReadLaterItem(
            document_id=document_id,
            position=position,
            note=note,
            expiry_days=expiry_days
        )
        
        self.read_later_items.append(item)
        self.save_items()
        return item
    
    def remove_item(self, document_id, position=None):
        """Remove Read Later item(s) for a document."""
        if position is None:
            # Remove all for this document
            self.read_later_items = [
                item for item in self.read_later_items if item.document_id != document_id
            ]
        else:
            # Remove specific position
            self.read_later_items = [
                item for item in self.read_later_items 
                if not (item.document_id == document_id and abs(item.position - position) < 100)
            ]
            
        self.save_items()
    
    def get_items_for_document(self, document_id):
        """Get all Read Later items for a document."""
        return [item for item in self.read_later_items if item.document_id == document_id]
    
    def load_items(self):
        """Load Read Later items from storage."""
        try:
            import json
            
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    items_data = json.load(f)
                    
                self.read_later_items = [
                    ReadLaterItem.from_dict(item) for item in items_data
                ]
                logger.info(f"Loaded {len(self.read_later_items)} Read Later items")
        except Exception as e:
            logger.exception(f"Error loading Read Later items: {e}")
            self.read_later_items = []
    
    def save_items(self):
        """Save Read Later items to storage."""
        try:
            import json
            
            # Convert items to dict for JSON serialization
            items_data = [item.to_dict() for item in self.read_later_items]
            
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(items_data, f)
                
            logger.info(f"Saved {len(self.read_later_items)} Read Later items")
        except Exception as e:
            logger.exception(f"Error saving Read Later items: {e}")
    
    def get_all_items(self):
        """Get all Read Later items."""
        return self.read_later_items

class ReadLaterDialog(QDialog):
    """Dialog for managing Read Later items."""
    
    itemSelected = pyqtSignal(int, float)  # document_id, position
    
    def __init__(self, db_session, parent=None):
        """Initialize dialog."""
        super().__init__(parent)
        self.db_session = db_session
        self.read_later_manager = ReadLaterManager(db_session)
        self._create_ui()
        self._load_items()
    
    def _create_ui(self):
        """Create the UI."""
        self.setWindowTitle("Read Later Items")
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout()
        
        # Create splitter for list and details
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side - list of items
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        
        self.items_list = QListWidget()
        self.items_list.setAlternatingRowColors(True)
        self.items_list.currentItemChanged.connect(self._on_item_selected)
        list_layout.addWidget(self.items_list)
        
        # Right side - item details
        details_widget = QWidget()
        details_layout = QVBoxLayout(details_widget)
        
        self.title_label = QLabel("Select an item")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        details_layout.addWidget(self.title_label)
        
        self.position_label = QLabel()
        details_layout.addWidget(self.position_label)
        
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("No note")
        self.note_edit.setReadOnly(True)
        details_layout.addWidget(self.note_edit)
        
        # Add widgets to splitter
        splitter.addWidget(list_widget)
        splitter.addWidget(details_widget)
        splitter.setSizes([200, 400])
        
        layout.addWidget(splitter)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.open_button = QPushButton("Open")
        self.open_button.clicked.connect(self._on_open)
        self.open_button.setEnabled(False)
        button_layout.addWidget(self.open_button)
        
        self.edit_note_button = QPushButton("Edit Note")
        self.edit_note_button.clicked.connect(self._on_edit_note)
        self.edit_note_button.setEnabled(False)
        button_layout.addWidget(self.edit_note_button)
        
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self._on_remove)
        self.remove_button.setEnabled(False)
        button_layout.addWidget(self.remove_button)
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _load_items(self):
        """Load items into the list."""
        self.items_list.clear()
        
        items = self.read_later_manager.get_all_items()
        if not items:
            # Add a message if no items
            item = QListWidgetItem("No Read Later items available")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.items_list.addItem(item)
            return
            
        # Get document titles
        document_titles = {}
        try:
            from core.knowledge_base.models import Document
            for document in self.db_session.query(Document).filter(
                Document.id.in_([item.document_id for item in items])
            ).all():
                document_titles[document.id] = document.title
        except Exception as e:
            logger.warning(f"Error loading document titles: {e}")
            
        # Sort items by timestamp (newest first)
        items.sort(key=lambda x: x.created_date, reverse=True)
        
        for item in items:
            # Create a friendly title
            title = document_titles.get(item.document_id, f"Document {item.document_id}")
            timestamp_str = item.created_date.strftime("%Y-%m-%d %H:%M") if item.created_date else "Unknown date"
            
            list_item = QListWidgetItem(f"{title} - {timestamp_str}")
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            
            # Add note indicator if present
            if item.note:
                list_item.setText(f"{list_item.text()} 📝")
                
            self.items_list.addItem(list_item)
    
    def _on_item_selected(self, current, previous):
        """Handle item selection."""
        if not current:
            self.open_button.setEnabled(False)
            self.edit_note_button.setEnabled(False)
            self.remove_button.setEnabled(False)
            self.title_label.setText("Select an item")
            self.position_label.setText("")
            self.note_edit.setText("")
            return
            
        item = current.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
            
        self.open_button.setEnabled(True)
        self.edit_note_button.setEnabled(True)
        self.remove_button.setEnabled(True)
        
        # Get document title
        try:
            from core.knowledge_base.models import Document
            document = self.db_session.query(Document).get(item.document_id)
            document_title = document.title if document else f"Document {item.document_id}"
        except Exception as e:
            logger.warning(f"Error loading document: {e}")
            document_title = f"Document {item.document_id}"
            
        self.title_label.setText(document_title)
        self.position_label.setText(f"Position: {item.position:.0f}")
        self.note_edit.setText(item.note or "")
    
    def _on_open(self):
        """Open the selected item."""
        current_item = self.items_list.currentItem()
        if not current_item:
            return
            
        item = current_item.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
            
        self.itemSelected.emit(item.document_id, item.position)
        self.accept()
    
    def _on_edit_note(self):
        """Edit the note for the selected item."""
        current_item = self.items_list.currentItem()
        if not current_item:
            return
            
        item = current_item.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
            
        note, ok = QInputDialog.getText(
            self,
            "Edit Note",
            "Enter a note for this position:",
            QLineEdit.EchoMode.Normal,
            item.note or ""
        )
        
        if not ok:
            return
            
        # Update the note
        item.note = note
        self.read_later_manager.save_items()
        
        # Update the UI
        self.note_edit.setText(note)
        if note:
            current_item.setText(current_item.text().rstrip(" 📝") + " 📝")
        else:
            current_item.setText(current_item.text().rstrip(" 📝"))
    
    def _on_remove(self):
        """Remove the selected item."""
        current_item = self.items_list.currentItem()
        if not current_item:
            return
            
        item = current_item.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
            
        # Confirm removal
        reply = QMessageBox.question(
            self,
            "Remove Item",
            "Are you sure you want to remove this Read Later item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
            
        # Remove the item
        self.read_later_manager.remove_item(item.document_id, item.position)
        
        # Reload the list
        self._load_items()
        
        # Clear details
        self.title_label.setText("Select an item")
        self.position_label.setText("")
        self.note_edit.setText("")
        self.open_button.setEnabled(False)
        self.edit_note_button.setEnabled(False)
        self.remove_button.setEnabled(False)
