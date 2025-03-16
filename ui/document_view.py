# If the patching approach doesn't work, here's a complete replacement for document_view.py
# Save this as ui/document_view.py.new and rename it if needed

import os
import logging
from typing import Optional, List, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QAction, QTextCursor, QColor, QTextCharFormat

from core.knowledge_base.models import Document, Extract
from core.content_extractor.extractor import ContentExtractor
from .extract_view import ExtractView

logger = logging.getLogger(__name__)

class DocumentView(QWidget):
    """UI component for viewing and processing documents."""
    
    def __init__(self, document: Document, db_session):
        super().__init__()
        
        self.document = document
        self.db_session = db_session
        self.extractor = ContentExtractor(db_session)
        
        # Content display variables
        self.content_text = ""
        self.selected_text = ""
        
        # Set up UI
        self._create_ui()
        self._load_document()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Document info area
        info_layout = QHBoxLayout()
        self.title_label = QLabel()
        info_layout.addWidget(self.title_label)
        info_layout.addStretch()
        
        # Extract button
        self.extract_button = QPushButton("Create Extract")
        self.extract_button.clicked.connect(self._on_create_extract)
        self.extract_button.setEnabled(False)  # Disabled until text is selected
        info_layout.addWidget(self.extract_button)
        
        # Auto-segment button
        self.segment_button = QPushButton("Auto-Segment")
        self.segment_button.clicked.connect(self._on_auto_segment)
        info_layout.addWidget(self.segment_button)
        
        main_layout.addLayout(info_layout)
        
        # Main content splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Document content area
        self.content_area = QWidget()
        content_layout = QVBoxLayout(self.content_area)
        
        # For PDF, we'd use a specialized viewer
        # For now, use a simple text editor for all content
        self.content_edit = QTextEdit()
        self.content_edit.setReadOnly(True)
        self.content_edit.selectionChanged.connect(self._on_selection_changed)
        self.content_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.content_edit.customContextMenuRequested.connect(self._on_content_menu)
        
        content_layout.addWidget(self.content_edit)
        
        # Extracts area
        self.extracts_area = QWidget()
        extracts_layout = QVBoxLayout(self.extracts_area)
        extracts_layout.addWidget(QLabel("Extracts:"))
        
        # Extracts list for this document
        self.extracts_list = QTextEdit()
        self.extracts_list.setReadOnly(True)
        extracts_layout.addWidget(self.extracts_list)
        
        # Add areas to splitter
        self.splitter.addWidget(self.content_area)
        self.splitter.addWidget(self.extracts_area)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(self.splitter)

    def _load_epub(self):
        """Load EPUB document content with proper encoding handling."""
        try:
            # Use the improved EPUB handler
            from core.document_processor.handlers.epub_handler import EPUBHandler

            handler = EPUBHandler()
            content = handler.extract_content(self.document.file_path)

            # Use markdown or HTML for display
            display_content = content['markdown'] if content['markdown'] else content['text']

            # Set document content
            self.content_text = display_content

            # Use setMarkdown if available (newer PyQt versions), otherwise use setText
            if hasattr(self.content_edit, 'setMarkdown'):
                self.content_edit.setMarkdown(display_content)
            else:
                self.content_edit.setText(display_content)

        except Exception as e:
            logger.exception(f"Error loading EPUB: {e}")
            self.content_edit.setText(f"Error loading EPUB: {str(e)}")
    
    def _load_document(self):
        """Load document content."""
        self.title_label.setText(f"{self.document.title}")
        
        # Load content based on document type
        if self.document.content_type == 'pdf':
            self._load_pdf()
        elif self.document.content_type in ['html', 'htm']:
            self._load_html()
        else:
            self._load_text()
        
        # Load existing extracts
        self._load_extracts()
    
    def _load_pdf(self):
        """Load PDF document content."""
        try:
            # In a real app, we'd use a specialized PDF viewer
            # For now, just extract text and display it
            from pdfminer.high_level import extract_text
            
            text = extract_text(self.document.file_path)
            self.content_text = text
            self.content_edit.setText(text)
            
        except Exception as e:
            logger.exception(f"Error loading PDF: {e}")
            self.content_edit.setText(f"Error loading PDF: {str(e)}")
    
    def _load_html(self):
        """Load HTML document content."""
        try:
            # In a real app, we might use a web view
            # For now, just extract text and display it
            from bs4 import BeautifulSoup
            
            with open(self.document.file_path, 'r', encoding='utf-8', errors='replace') as file:
                html_content = file.read()
            
            soup = BeautifulSoup(html_content, 'lxml')
            text = soup.get_text(separator='\n')
            
            self.content_text = text
            self.content_edit.setText(text)
            
        except Exception as e:
            logger.exception(f"Error loading HTML: {e}")
            self.content_edit.setText(f"Error loading HTML: {str(e)}")
    
    def _load_text(self):
        """Load text document content."""
        try:
            # Try UTF-8 first
            try:
                with open(self.document.file_path, 'r', encoding='utf-8') as file:
                    text = file.read()
            except UnicodeDecodeError:
                # If UTF-8 fails, try other common encodings
                encodings = ['latin-1', 'windows-1252', 'iso-8859-1', 'cp1252']
                
                for encoding in encodings:
                    try:
                        with open(self.document.file_path, 'r', encoding=encoding) as file:
                            text = file.read()
                        logger.info(f"Successfully read file using {encoding} encoding")
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    # If all encodings fail, read as binary and decode as best as possible
                    with open(self.document.file_path, 'rb') as file:
                        binary_data = file.read()
                    
                    # Try to decode with errors='replace' to replace invalid characters
                    text = binary_data.decode('utf-8', errors='replace')
                    logger.warning("Using fallback decoding with replacement characters")
            
            self.content_text = text
            self.content_edit.setText(text)
            
        except Exception as e:
            logger.exception(f"Error loading text: {e}")
            self.content_edit.setText(f"Error loading text: {str(e)}")
    
    def _load_extracts(self):
        """Load existing extracts for this document."""
        extracts = self.db_session.query(Extract).filter(
            Extract.document_id == self.document.id
        ).order_by(Extract.created_date.desc()).all()
        
        if not extracts:
            self.extracts_list.setText("No extracts yet")
            return
        
        # Display extracts
        text = ""
        for extract in extracts:
            text += f"Priority: {extract.priority}\n"
            text += f"{extract.content[:100]}...\n"
            text += f"Created: {extract.created_date}\n"
            text += "-" * 40 + "\n"
        
        self.extracts_list.setText(text)
    
    @pyqtSlot()
    def _on_selection_changed(self):
        """Handle text selection changes."""
        self.selected_text = self.content_edit.textCursor().selectedText()
        self.extract_button.setEnabled(bool(self.selected_text))
    
    @pyqtSlot()
    def _on_create_extract(self):
        """Create an extract from selected text."""
        if not self.selected_text:
            return
        
        # Get surrounding context
        cursor = self.content_edit.textCursor()
        position = cursor.position()
        
        # Try to get some context before and after selection
        start_pos = max(0, position - 100)
        end_pos = min(len(self.content_text), position + 100)
        
        context = self.content_text[start_pos:end_pos]
        
        # Create extract
        extract = self.extractor.create_extract(
            document_id=self.document.id,
            content=self.selected_text,
            context=context,
            position=f"pos:{position}",
            priority=50  # Default priority
        )
        
        if extract:
            # Reload extracts
            self._load_extracts()
            
            # Open extract view
            self._open_extract(extract)
        else:
            QMessageBox.warning(
                self, "Extract Creation Failed", 
                "Failed to create extract"
            )
    
    @pyqtSlot()
    def _on_auto_segment(self):
        """Auto-segment the document into potential extracts."""
        # Get segments
        segments = self.extractor.auto_segment_content(self.document.id)
        
        if not segments:
            QMessageBox.information(
                self, "Auto-Segment", 
                "No segments were identified in this document"
            )
            return
        
        # Create extracts for segments
        for segment in segments:
            extract = self.extractor.create_extract(
                document_id=self.document.id,
                content=segment['content'],
                position=segment.get('position', ''),
                priority=segment.get('priority', 50)
            )
        
        # Reload extracts
        self._load_extracts()
        
        QMessageBox.information(
            self, "Auto-Segment", 
            f"Created {len(segments)} extracts from this document"
        )
    
    @pyqtSlot(QPoint)
    def _on_content_menu(self, pos):
        """Show context menu for content."""
        # Create menu
        menu = QMenu(self)
        
        # Add actions
        create_extract_action = menu.addAction("Create Extract")
        create_extract_action.triggered.connect(self._on_create_extract)
        
        # Show menu
        menu.exec(self.content_edit.mapToGlobal(pos))
    
    def _open_extract(self, extract: Extract):
        """Open an extract in the parent tab widget."""
        extract_view = ExtractView(extract, self.db_session)
        
        # We need to find the parent tab widget
        # This is a bit hacky - in a real app, we'd use signals/slots
        parent = self.parent()
        while parent and not isinstance(parent, QTabWidget):
            parent = parent.parent()
        
        if parent:
            tab_index = parent.addTab(extract_view, "Extract")
            parent.setCurrentIndex(tab_index)
