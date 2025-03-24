import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QDialog, QListWidget, QListWidgetItem, QSplitter, QMenu,
    QMessageBox, QSlider, QComboBox
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
        """Load Read Later items from database."""
        try:
            from sqlalchemy import Column, Integer, String, DateTime, Float, Text
            from sqlalchemy.ext.declarative import declarative_base
            from core.knowledge_base.models import Document
            import json
            from sqlalchemy import text
            
            # Get all items from read_later table
            # Check if the table exists first
            if not self._ensure_read_later_table():
                return
                
            # Execute raw query
            result = self.db_session.execute(text("SELECT * FROM read_later"))
            
            items = []
            for row in result:
                try:
                    data = json.loads(row.data)
                    item = ReadLaterItem.from_dict(data)
                    items.append(item)
                except Exception as e:
                    logger.error(f"Error loading read later item: {e}")
            
            # Filter out expired items
            self.read_later_items = [item for item in items if not item.is_expired()]
            
            # Save to remove expired items
            if len(items) != len(self.read_later_items):
                self.save_items()
                
            logger.info(f"Loaded {len(self.read_later_items)} read later items")
                
        except Exception as e:
            logger.exception(f"Error loading read later items: {e}")
            self.read_later_items = []
    
    def save_items(self):
        """Save Read Later items to database."""
        try:
            import json
            from sqlalchemy import text
            
            # Ensure table exists
            if not self._ensure_read_later_table():
                return
                
            # Clear existing items
            self.db_session.execute(text("DELETE FROM read_later"))
            
            # Insert new items
            for item in self.read_later_items:
                data = json.dumps(item.to_dict())
                self.db_session.execute(
                    text("INSERT INTO read_later (document_id, position, data) VALUES (:doc_id, :pos, :data)"),
                    {"doc_id": item.document_id, "pos": item.position, "data": data}
                )
                
            self.db_session.commit()
            logger.info(f"Saved {len(self.read_later_items)} read later items")
                
        except Exception as e:
            logger.exception(f"Error saving read later items: {e}")
    
    def _ensure_read_later_table(self):
        """Ensure the read_later table exists."""
        try:
            # Check if table exists
            from sqlalchemy import text
            result = self.db_session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='read_later'"))
            if not result.fetchone():
                # Create table
                self.db_session.execute(text("""
                CREATE TABLE read_later (
                    id INTEGER PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    position REAL NOT NULL,
                    data TEXT NOT NULL
                )
                """))
                self.db_session.commit()
                logger.info("Created read_later table")
            return True
        except Exception as e:
            logger.exception(f"Error ensuring read_later table: {e}")
            return False

class ReadLaterDialog(QDialog):
    """Dialog for managing Read Later items."""
    
    itemSelected = pyqtSignal(int, float)  # document_id, position
    
    def __init__(self, db_session, parent=None):
        """Initialize dialog."""
        super().__init__(parent)
        self.db_session = db_session
        self.manager = ReadLaterManager(db_session)
        self._create_ui()
        self._load_items()
    
    def _create_ui(self):
        """Create the UI."""
        self.setWindowTitle("Read Later Items")
        self.resize(500, 400)
        
        layout = QVBoxLayout()
        
        # List widget for items
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.itemDoubleClicked.connect(self._on_item_activated)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.list_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._load_items)
        button_layout.addWidget(self.refresh_button)
        
        self.open_button = QPushButton("Open Selected")
        self.open_button.clicked.connect(self._on_open_selected)
        button_layout.addWidget(self.open_button)
        
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._on_remove_selected)
        button_layout.addWidget(self.remove_button)
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _load_items(self):
        """Load items into list widget."""
        self.list_widget.clear()
        
        # Reload items
        self.manager.load_items()
        
        # Group items by document
        documents = {}
        for item in self.manager.read_later_items:
            if item.document_id not in documents:
                # Get document info
                from core.knowledge_base.models import Document
                document = self.db_session.query(Document).get(item.document_id)
                if document:
                    documents[item.document_id] = {
                        'document': document,
                        'items': []
                    }
                else:
                    continue
            
            documents[item.document_id]['items'].append(item)
        
        # Add items to list
        for doc_id, data in documents.items():
            document = data['document']
            
            # Create document header item
            doc_item = QListWidgetItem(f"📄 {document.title}")
            doc_item.setBackground(QColor(240, 240, 250))
            doc_item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            doc_item.setData(Qt.ItemDataRole.UserRole, {'type': 'header', 'document_id': doc_id})
            self.list_widget.addItem(doc_item)
            
            # Add document items
            for item in data['items']:
                # Get position description
                position_desc = self._get_position_description(document, item.position)
                
                # Create item
                list_item = QListWidgetItem(f"    • {position_desc}")
                if item.note:
                    list_item.setText(f"    • {position_desc} - \"{item.note}\"")
                
                # Store data
                list_item.setData(Qt.ItemDataRole.UserRole, {
                    'type': 'bookmark',
                    'document_id': doc_id,
                    'position': item.position,
                    'note': item.note
                })
                
                # Add item
                self.list_widget.addItem(list_item)
    
    def _get_position_description(self, document, position):
        """Get description of position in document."""
        if not document:
            return f"Position: {position}"
            
        # Different descriptions based on document type
        doc_type = document.content_type.lower() if hasattr(document, 'content_type') and document.content_type else "text"
        
        if doc_type == "pdf":
            # For PDFs, position is usually page number
            return f"Page {int(position)}"
        elif doc_type in ["epub", "html", "htm"]:
            # For web-based content, estimate percent through document
            # This would be more accurate if we knew the total document height
            return f"Position: {position:.0f} (scroll units)"
        elif doc_type in ["mp3", "wav", "ogg", "flac", "m4a", "aac"]:
            # For audio, convert position to time
            minutes = int(position / 60)
            seconds = int(position % 60)
            return f"Time: {minutes}:{seconds:02d}"
        else:
            return f"Position: {position:.0f}"
    
    def _on_item_activated(self, item):
        """Handle double-click on item."""
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data['type'] == 'bookmark':
            self.itemSelected.emit(data['document_id'], data['position'])
            self.accept()
    
    def _on_open_selected(self):
        """Open selected item."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if data:
            if data['type'] == 'header':
                # Open document at beginning
                self.itemSelected.emit(data['document_id'], 0)
            elif data['type'] == 'bookmark':
                # Open document at bookmark position
                self.itemSelected.emit(data['document_id'], data['position'])
            
            self.accept()
    
    def _on_remove_selected(self):
        """Remove selected item."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if data:
            if data['type'] == 'header':
                # Remove all bookmarks for this document
                if QMessageBox.question(
                    self,
                    "Remove All",
                    f"Remove all bookmarks for this document?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                ) == QMessageBox.StandardButton.Yes:
                    self.manager.remove_item(data['document_id'])
                    self._load_items()
            elif data['type'] == 'bookmark':
                # Remove specific bookmark
                self.manager.remove_item(data['document_id'], data['position'])
                self._load_items()
    
    def _show_context_menu(self, position):
        """Show context menu for item."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
            
        data = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if not data:
            return
            
        menu = QMenu(self)
        
        if data['type'] == 'header':
            # Document header
            open_action = QAction("Open Document", self)
            open_action.triggered.connect(self._on_open_selected)
            menu.addAction(open_action)
            
            remove_all_action = QAction("Remove All Bookmarks", self)
            remove_all_action.triggered.connect(self._on_remove_selected)
            menu.addAction(remove_all_action)
            
        elif data['type'] == 'bookmark':
            # Bookmark
            open_action = QAction("Open at This Position", self)
            open_action.triggered.connect(self._on_open_selected)
            menu.addAction(open_action)
            
            remove_action = QAction("Remove Bookmark", self)
            remove_action.triggered.connect(self._on_remove_selected)
            menu.addAction(remove_action)
            
            # Edit note
            edit_note_action = QAction("Edit Note", self)
            edit_note_action.triggered.connect(lambda: self._edit_bookmark_note(data))
            menu.addAction(edit_note_action)
        
        menu.exec(self.list_widget.mapToGlobal(position))
    
    def _edit_bookmark_note(self, data):
        """Edit bookmark note."""
        from PyQt6.QtWidgets import QInputDialog
        
        # Get current note
        current_note = data.get('note', '')
        
        # Show input dialog
        new_note, ok = QInputDialog.getText(
            self,
            "Edit Note",
            "Enter note for this bookmark:",
        )
