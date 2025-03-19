import os
import json
import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QSplitter, QMessageBox,
    QListWidget, QListWidgetItem, QMenu, QScrollBar
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QAction, QTextCursor, QFont

from core.knowledge_base.models import Extract

logger = logging.getLogger(__name__)

class YouTubeTranscriptView(QWidget):
    """Widget for displaying and interacting with YouTube video transcripts."""
    
    extractCreated = pyqtSignal(int)  # extract_id

    def __init__(self, db_session, document_id=None, metadata_file=None):
        super().__init__()
        
        self.db_session = db_session
        self.document_id = document_id
        self.metadata_file = metadata_file
        self.transcript_text = ""
        self.selected_text = ""
        
        # Create UI
        self._create_ui()
        
        # Load transcript if available
        if self.metadata_file:
            self._load_transcript_from_file()
    
    def _create_ui(self):
        """Create the UI components."""
        main_layout = QVBoxLayout(self)
        
        # Header section
        header_layout = QHBoxLayout()
        
        self.title_label = QLabel("Transcript")
        self.title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        self.create_extract_btn = QPushButton("Create Extract from Selection")
        self.create_extract_btn.setEnabled(False)
        self.create_extract_btn.clicked.connect(self._on_create_extract)
        header_layout.addWidget(self.create_extract_btn)
        
        main_layout.addLayout(header_layout)
        
        # Transcript display
        self.transcript_edit = QTextEdit()
        self.transcript_edit.setReadOnly(True)
        self.transcript_edit.setPlaceholderText("No transcript available for this video.")
        self.transcript_edit.selectionChanged.connect(self._on_selection_changed)
        self.transcript_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.transcript_edit.customContextMenuRequested.connect(self._on_context_menu)
        
        main_layout.addWidget(self.transcript_edit)
        
        # Status label
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)
    
    def _load_transcript_from_file(self):
        """Load transcript from the metadata file."""
        if not os.path.exists(self.metadata_file):
            self.status_label.setText("Metadata file not found")
            return
        
        try:
            # Load metadata file
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            # Check if transcript is available
            transcript = metadata.get('transcript')
            if not transcript:
                self.status_label.setText("No transcript available for this video")
                return
            
            # Set transcript text
            self.transcript_text = transcript
            self.transcript_edit.setText(transcript)
            
            # Update UI
            self.title_label.setText(f"Transcript: {metadata.get('title', 'YouTube Video')}")
            self.status_label.setText("Transcript loaded successfully")
            
        except Exception as e:
            logger.exception(f"Error loading transcript: {e}")
            self.status_label.setText(f"Error loading transcript: {str(e)}")
    
    def set_document_id(self, document_id):
        """Set the document ID for extract creation."""
        self.document_id = document_id
    
    def set_metadata_file(self, metadata_file):
        """Set the metadata file path and load transcript."""
        self.metadata_file = metadata_file
        self._load_transcript_from_file()
    
    @pyqtSlot()
    def _on_selection_changed(self):
        """Handle text selection change."""
        # Get selected text
        cursor = self.transcript_edit.textCursor()
        self.selected_text = cursor.selectedText()
        
        # Enable/disable extract button
        self.create_extract_btn.setEnabled(bool(self.selected_text))
    
    @pyqtSlot(QPoint)
    def _on_context_menu(self, pos):
        """Show context menu for the transcript text."""
        menu = QMenu(self)
        
        # Add actions depending on selection
        if self.selected_text:
            extract_action = QAction("Create Extract", self)
            extract_action.triggered.connect(self._on_create_extract)
            menu.addAction(extract_action)
            
            menu.addSeparator()
            
            copy_action = QAction("Copy", self)
            copy_action.triggered.connect(self.transcript_edit.copy)
            menu.addAction(copy_action)
        else:
            copy_action = QAction("Copy", self)
            copy_action.triggered.connect(self.transcript_edit.copy)
            menu.addAction(copy_action)
            
            select_all_action = QAction("Select All", self)
            select_all_action.triggered.connect(self.transcript_edit.selectAll)
            menu.addAction(select_all_action)
        
        # Show menu
        menu.exec(self.transcript_edit.mapToGlobal(pos))
    
    @pyqtSlot()
    def _on_create_extract(self):
        """Create an extract from the selected text."""
        if not self.selected_text:
            QMessageBox.warning(
                self, "No Selection", 
                "Please select text from the transcript to create an extract."
            )
            return
        
        if not self.document_id:
            QMessageBox.warning(
                self, "No Document", 
                "Document ID not available. Cannot create extract."
            )
            return
        
        try:
            # Get context (surrounding text)
            cursor = self.transcript_edit.textCursor()
            selection_start = cursor.selectionStart()
            selection_end = cursor.selectionEnd()
            
            # Get a bit of context before and after selection
            context_start = max(0, selection_start - 100)
            context_end = min(len(self.transcript_text), selection_end + 100)
            
            # Extract context
            cursor.setPosition(context_start)
            cursor.setPosition(context_end, QTextCursor.MoveMode.KeepAnchor)
            context = cursor.selectedText()
            
            # Create the extract
            extract = Extract(
                content=self.selected_text,
                context=context,
                document_id=self.document_id,
                position=f"transcript:{selection_start}-{selection_end}",
                created_date=datetime.utcnow()
            )
            
            # Add to database
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Emit signal
            self.extractCreated.emit(extract.id)
            
            # Update status
            self.status_label.setText(f"Extract created: {self.selected_text[:30]}...")
            
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to create extract: {str(e)}"
            )
    
    def get_transcript_text(self):
        """Get the full transcript text."""
        return self.transcript_text 