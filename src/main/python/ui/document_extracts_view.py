import logging
from typing import List, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QColor

from core.knowledge_base.models import Extract, Document

logger = logging.getLogger(__name__)

class DocumentExtractsView(QWidget):
    """Widget for displaying extracts for a specific document."""
    
    extractSelected = pyqtSignal(int)  # extract_id
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.document_id = None
        self.current_extract = None
        
        # Set up UI
        self._create_ui()
    
    def _create_ui(self):
        """Create the UI components."""
        # Main layout
        layout = QVBoxLayout(self)
        
        # Header label
        self.header_label = QLabel("Document Extracts")
        layout.addWidget(self.header_label)
        
        # Extracts table
        self.extracts_table = QTableWidget()
        self.extracts_table.setColumnCount(3)
        self.extracts_table.setHorizontalHeaderLabels(["Content", "Date", "Priority"])
        self.extracts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.extracts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.extracts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.extracts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.extracts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.extracts_table.doubleClicked.connect(self._on_extract_double_clicked)
        self.extracts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.extracts_table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.extracts_table)
        
        # Preview section
        preview_layout = QVBoxLayout()
        
        preview_label = QLabel("Extract Preview")
        preview_layout.addWidget(preview_label)
        
        self.extract_preview = QTextEdit()
        self.extract_preview.setReadOnly(True)
        preview_layout.addWidget(self.extract_preview)
        
        layout.addLayout(preview_layout)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        
        self.open_button = QPushButton("Open Extract")
        self.open_button.clicked.connect(self._on_open_extract)
        self.open_button.setEnabled(False)
        buttons_layout.addWidget(self.open_button)
        
        buttons_layout.addStretch()
        
        self.count_label = QLabel("0 extracts")
        buttons_layout.addWidget(self.count_label)
        
        layout.addLayout(buttons_layout)
    
    def load_extracts_for_document(self, document_id):
        """Load extracts for a specific document."""
        self.document_id = document_id
        
        # Get document title
        document = self.db_session.query(Document).get(document_id)
        if document:
            self.header_label.setText(f"Extracts for: {document.title}")
        
        # Clear current extracts
        self.extracts_table.setRowCount(0)
        
        # Query extracts for this document
        extracts = self.db_session.query(Extract).filter(
            Extract.document_id == document_id
        ).order_by(Extract.created_date.desc()).all()
        
        # Update count label
        self.count_label.setText(f"{len(extracts)} extracts")
        
        # Add extracts to table
        for i, extract in enumerate(extracts):
            self.extracts_table.insertRow(i)
            
            # Truncate content if too long
            content = extract.content
            if len(content) > 100:
                content = content[:97] + "..."
            
            # Extract content
            content_item = QTableWidgetItem(content)
            content_item.setData(Qt.ItemDataRole.UserRole, extract.id)
            self.extracts_table.setItem(i, 0, content_item)
            
            # Date created
            date_str = extract.created_date.strftime("%Y-%m-%d %H:%M") if extract.created_date else ""
            date_item = QTableWidgetItem(date_str)
            self.extracts_table.setItem(i, 1, date_item)
            
            # Priority
            priority_item = QTableWidgetItem(str(extract.priority))
            self.extracts_table.setItem(i, 2, priority_item)
            
            # Color row based on priority
            if extract.priority >= 80:
                # High priority - light red
                color = QColor(255, 200, 200)
            elif extract.priority >= 60:
                # Medium-high priority - light orange
                color = QColor(255, 225, 200)
            elif extract.priority <= 20:
                # Low priority - light blue
                color = QColor(200, 200, 255)
            else:
                # Normal priority - no color
                continue
                
            # Apply color to row
            for j in range(self.extracts_table.columnCount()):
                self.extracts_table.item(i, j).setBackground(color)
    
    def _on_extract_double_clicked(self, index):
        """Handle double-click on extract row."""
        if not index.isValid():
            return
        
        # Get extract ID
        row = index.row()
        extract_id = self.extracts_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # Emit signal
        self.extractSelected.emit(extract_id)
    
    @pyqtSlot(QPoint)
    def _on_context_menu(self, pos):
        """Show context menu for extracts table."""
        index = self.extracts_table.indexAt(pos)
        if not index.isValid():
            return
        
        # Get extract ID
        row = index.row()
        extract_id = self.extracts_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # Load extract
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            return
            
        self.current_extract = extract
        
        # Create menu
        menu = QMenu(self)
        
        # Add actions
        open_action = menu.addAction("Open Extract")
        open_action.triggered.connect(self._on_open_extract)
        
        menu.addSeparator()
        
        copy_action = menu.addAction("Copy Content")
        copy_action.triggered.connect(self._on_copy_content)
        
        # Show menu
        menu.exec(self.extracts_table.viewport().mapToGlobal(pos))
    
    def _on_open_extract(self):
        """Handle opening the selected extract."""
        if not self.current_extract:
            # Check if any row is selected
            selected_items = self.extracts_table.selectedItems()
            if not selected_items:
                return
                
            # Get extract ID from selected row
            row = selected_items[0].row()
            extract_id = self.extracts_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            
            # Emit signal
            self.extractSelected.emit(extract_id)
        else:
            # Use current extract
            self.extractSelected.emit(self.current_extract.id)
    
    def _on_copy_content(self):
        """Copy extract content to clipboard."""
        if not self.current_extract:
            return
            
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.current_extract.content)
        
    def _update_preview(self):
        """Update the extract preview."""
        # Clear preview
        self.extract_preview.clear()
        
        if not self.current_extract:
            return
            
        # Set content
        self.extract_preview.setText(self.current_extract.content)
        
        # Enable open button
        self.open_button.setEnabled(True) 