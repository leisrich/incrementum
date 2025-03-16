# ui/browse_extracts_view.py

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QComboBox, QCheckBox, QGroupBox,
    QFormLayout, QSpinBox, QMenu, QApplication,
    QSplitter, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QColor, QIcon

from sqlalchemy import func, and_, or_, not_
from core.knowledge_base.models import Extract, Document, Tag, Category

logger = logging.getLogger(__name__)

class BrowseExtractsView(QWidget):
    """Widget for browsing all extracts with filtering options."""
    
    extractSelected = pyqtSignal(int)  # extract_id
    extractDeleted = pyqtSignal()
    documentSelected = pyqtSignal(int)  # document_id
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.current_extract = None
        
        # Create UI
        self._create_ui()
        
        # Load initial data
        self._load_extracts()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header
        header_layout = QHBoxLayout()
        
        header_label = QLabel("<h2>Browse Extracts</h2>")
        header_layout.addWidget(header_label)
        
        header_layout.addStretch()
        
        # Refresh button
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._on_refresh)
        header_layout.addWidget(refresh_button)
        
        main_layout.addLayout(header_layout)
        
        # Create splitter for top/bottom sections
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Top section (filters and table)
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Filters
        filters_group = QGroupBox("Filters")
        filters_layout = QHBoxLayout(filters_group)
        
        # Document filter
        doc_layout = QFormLayout()
        self.document_combo = QComboBox()
        self.document_combo.addItem("All Documents", None)
        self._populate_documents()
        self.document_combo.currentIndexChanged.connect(self._on_filter_changed)
        doc_layout.addRow("Document:", self.document_combo)
        
        # Only show processed/unprocessed
        self.processed_checkbox = QCheckBox("Show only processed")
        self.processed_checkbox.stateChanged.connect(self._on_filter_changed)
        
        self.unprocessed_checkbox = QCheckBox("Show only unprocessed")
        self.unprocessed_checkbox.stateChanged.connect(self._on_filter_changed)
        
        doc_layout.addRow("Filter:", self.processed_checkbox)
        doc_layout.addRow("", self.unprocessed_checkbox)
        
        filters_layout.addLayout(doc_layout)
        
        # Tag filter
        tag_layout = QFormLayout()
        self.tag_combo = QComboBox()
        self.tag_combo.addItem("All Tags", None)
        self._populate_tags()
        self.tag_combo.currentIndexChanged.connect(self._on_filter_changed)
        tag_layout.addRow("Tag:", self.tag_combo)
        
        # Priority filter
        self.min_priority = QSpinBox()
        self.min_priority.setRange(0, 100)
        self.min_priority.setValue(0)
        self.min_priority.valueChanged.connect(self._on_filter_changed)
        tag_layout.addRow("Min Priority:", self.min_priority)
        
        self.max_priority = QSpinBox()
        self.max_priority.setRange(0, 100)
        self.max_priority.setValue(100)
        self.max_priority.valueChanged.connect(self._on_filter_changed)
        tag_layout.addRow("Max Priority:", self.max_priority)
        
        filters_layout.addLayout(tag_layout)
        
        # Category filter
        cat_layout = QFormLayout()
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        self._populate_categories()
        self.category_combo.currentIndexChanged.connect(self._on_filter_changed)
        cat_layout.addRow("Category:", self.category_combo)
        
        filters_layout.addLayout(cat_layout)
        
        top_layout.addWidget(filters_group)
        
        # Extracts table
        self.extracts_table = QTableWidget()
        self.extracts_table.setColumnCount(5)
        self.extracts_table.setHorizontalHeaderLabels(["Content", "Document", "Priority", "Date", "Processed"])
        self.extracts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.extracts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.extracts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.extracts_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.extracts_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.extracts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.extracts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.extracts_table.selectionChanged = self._on_selection_changed
        self.extracts_table.doubleClicked.connect(self._on_extract_double_clicked)
        self.extracts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.extracts_table.customContextMenuRequested.connect(self._on_context_menu)
        
        top_layout.addWidget(self.extracts_table)
        
        # Bottom section (extract preview)
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        # Preview label
        preview_label = QLabel("Extract Preview")
        bottom_layout.addWidget(preview_label)
        
        # Extract content preview
        self.extract_preview = QTextEdit()
        self.extract_preview.setReadOnly(True)
        bottom_layout.addWidget(self.extract_preview)
        
        # Extract metadata
        metadata_layout = QHBoxLayout()
        
        self.tags_label = QLabel("Tags: ")
        metadata_layout.addWidget(self.tags_label)
        
        metadata_layout.addStretch()
        
        self.document_label = QLabel("Document: ")
        metadata_layout.addWidget(self.document_label)
        
        bottom_layout.addLayout(metadata_layout)
        
        # Action buttons
        buttons_layout = QHBoxLayout()
        
        self.edit_button = QPushButton("Edit Extract")
        self.edit_button.clicked.connect(self._on_edit_extract)
        self.edit_button.setEnabled(False)
        buttons_layout.addWidget(self.edit_button)
        
        self.open_document_button = QPushButton("Open Source Document")
        self.open_document_button.clicked.connect(self._on_open_document)
        self.open_document_button.setEnabled(False)
        buttons_layout.addWidget(self.open_document_button)
        
        buttons_layout.addStretch()
        
        self.delete_button = QPushButton("Delete Extract")
        self.delete_button.clicked.connect(self._on_delete_extract)
        self.delete_button.setEnabled(False)
        buttons_layout.addWidget(self.delete_button)
        
        bottom_layout.addLayout(buttons_layout)
        
        # Add widgets to splitter
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # Status area
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)
        
        self.count_label = QLabel("0 extracts")
        status_layout.addWidget(self.count_label)
        
        main_layout.addLayout(status_layout)
    
    def _populate_documents(self):
        """Populate the document combo box."""
        # Clear current items (except "All Documents")
        while self.document_combo.count() > 1:
            self.document_combo.removeItem(1)
        
        # Get documents
        documents = self.db_session.query(Document).order_by(Document.title).all()
        
        # Add to combo box
        for doc in documents:
            self.document_combo.addItem(doc.title, doc.id)
    
    def _populate_tags(self):
        """Populate the tag combo box."""
        # Clear current items (except "All Tags")
        while self.tag_combo.count() > 1:
            self.tag_combo.removeItem(1)
        
        # Get tags
        tags = self.db_session.query(Tag).order_by(Tag.name).all()
        
        # Add to combo box
        for tag in tags:
            self.tag_combo.addItem(tag.name, tag.id)
    
    def _populate_categories(self):
        """Populate the category combo box."""
        # Clear current items (except "All Categories")
        while self.category_combo.count() > 1:
            self.category_combo.removeItem(1)
        
        # Get categories
        categories = self.db_session.query(Category).order_by(Category.name).all()
        
        # Add to combo box
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
    
    def _load_extracts(self):
        """Load extracts based on current filters."""
        # Clear table
        self.extracts_table.setRowCount(0)
        
        # Build query
        query = self.db_session.query(Extract).join(
            Document, Extract.document_id == Document.id
        )
        
        # Apply filters
        # Document filter
        document_id = self.document_combo.currentData()
        if document_id is not None:
            query = query.filter(Extract.document_id == document_id)
        
        # Tag filter
        tag_id = self.tag_combo.currentData()
        if tag_id is not None:
            query = query.filter(Extract.tags.any(Tag.id == tag_id))
        
        # Priority filter
        min_priority = self.min_priority.value()
        max_priority = self.max_priority.value()
        query = query.filter(Extract.priority.between(min_priority, max_priority))
        
        # Category filter
        category_id = self.category_combo.currentData()
        if category_id is not None:
            query = query.filter(Document.category_id == category_id)
        
        # Processed/unprocessed filter
        if self.processed_checkbox.isChecked() and not self.unprocessed_checkbox.isChecked():
            query = query.filter(Extract.processed == True)
        elif self.unprocessed_checkbox.isChecked() and not self.processed_checkbox.isChecked():
            query = query.filter(Extract.processed == False)
        elif self.processed_checkbox.isChecked() and self.unprocessed_checkbox.isChecked():
            # This essentially means "show all" so no filter needed
            pass
        
        # Order by creation date (newest first)
        query = query.order_by(Extract.created_date.desc())
        
        # Execute query
        extracts = query.all()
        
        # Update count
        self.count_label.setText(f"{len(extracts)} extracts")
        
        # Populate table
        for i, extract in enumerate(extracts):
            self.extracts_table.insertRow(i)
            
            # Content
            content = extract.content
            if len(content) > 100:
                content = content[:97] + "..."
            
            content_item = QTableWidgetItem(content)
            content_item.setData(Qt.ItemDataRole.UserRole, extract.id)
            self.extracts_table.setItem(i, 0, content_item)
            
            # Document
            doc_title = extract.document.title if extract.document else "No document"
            doc_item = QTableWidgetItem(doc_title)
            doc_item.setData(Qt.ItemDataRole.UserRole, extract.document_id if extract.document else None)
            self.extracts_table.setItem(i, 1, doc_item)
            
            # Priority
            priority_item = QTableWidgetItem(str(extract.priority))
            
            # Color based on priority
            if extract.priority >= 80:
                priority_item.setBackground(QColor(255, 200, 200))  # Light red for high priority
            elif extract.priority >= 50:
                priority_item.setBackground(QColor(255, 255, 200))  # Light yellow for medium priority
            else:
                priority_item.setBackground(QColor(200, 255, 200))  # Light green for low priority
                
            self.extracts_table.setItem(i, 2, priority_item)
            
            # Date
            date_str = extract.created_date.strftime("%Y-%m-%d") if extract.created_date else ""
            date_item = QTableWidgetItem(date_str)
            self.extracts_table.setItem(i, 3, date_item)
            
            # Processed
            processed_item = QTableWidgetItem("Yes" if extract.processed else "No")
            
            # Color based on processed status
            if extract.processed:
                processed_item.setBackground(QColor(200, 255, 200))  # Light green
            else:
                processed_item.setBackground(QColor(255, 200, 200))  # Light red
                
            self.extracts_table.setItem(i, 4, processed_item)
        
        # Clear current extract
        self.current_extract = None
        self._update_preview()
        
        # Update status
        self.status_label.setText("Extracts loaded")
    
    def _update_preview(self):
        """Update the extract preview area."""
        if self.current_extract:
            # Set content
            self.extract_preview.setText(self.current_extract.content)
            
            # Set tags
            tag_names = [tag.name for tag in self.current_extract.tags]
            self.tags_label.setText(f"Tags: {', '.join(tag_names) if tag_names else 'None'}")
            
            # Set document
            if self.current_extract.document:
                self.document_label.setText(f"Document: {self.current_extract.document.title}")
                self.open_document_button.setEnabled(True)
            else:
                self.document_label.setText("Document: None")
                self.open_document_button.setEnabled(False)
            
            # Enable buttons
            self.edit_button.setEnabled(True)
            self.delete_button.setEnabled(True)
        else:
            # Clear preview
            self.extract_preview.clear()
            self.tags_label.setText("Tags: ")
            self.document_label.setText("Document: ")
            
            # Disable buttons
            self.edit_button.setEnabled(False)
            self.open_document_button.setEnabled(False)
            self.delete_button.setEnabled(False)
    
    def _on_selection_changed(self):
        """Handle selection change in extracts table."""
        selected_indexes = self.extracts_table.selectedIndexes()
        if not selected_indexes:
            self.current_extract = None
            self._update_preview()
            return
        
        # Get first selected row
        row = selected_indexes[0].row()
        extract_id = self.extracts_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # Load extract
        self.current_extract = self.db_session.query(Extract).get(extract_id)
        self._update_preview()
    
    @pyqtSlot(QPoint)
    def _on_context_menu(self, pos):
        """Show context menu for extracts table."""
        index = self.extracts_table.indexAt(pos)
        if not index.isValid():
            return
        
        # Get extract ID
        row = index.row()
        extract_id = self.extracts_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        
        # Add actions
        edit_action = menu.addAction("Edit Extract")
        edit_action.triggered.connect(lambda: self._on_edit_extract())
        
        # Check if extract has a document
        document_id = self.extracts_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        if document_id:
            open_doc_action = menu.addAction("Open Source Document")
            open_doc_action.triggered.connect(lambda: self._on_open_document())
        
        menu.addSeparator()
        
        copy_action = menu.addAction("Copy Content")
        copy_action.triggered.connect(lambda: self._on_copy_content())
        
        menu.addSeparator()
        
        delete_action = menu.addAction("Delete Extract")
        delete_action.triggered.connect(lambda: self._on_delete_extract())
        
        menu.exec(self.extracts_table.viewport().mapToGlobal(pos))
    
    @pyqtSlot()
    def _on_edit_extract(self):
        """Handle edit extract button click."""
        if not self.current_extract:
            return
        
        # Emit signal
        self.extractSelected.emit(self.current_extract.id)
    
    @pyqtSlot()
    def _on_open_document(self):
        """Handle open document button click."""
        if not self.current_extract or not self.current_extract.document:
            return
        
        # Emit signal
        self.documentSelected.emit(self.current_extract.document_id)
    
    @pyqtSlot()
    def _on_delete_extract(self):
        """Handle delete extract button click."""
        if not self.current_extract:
            return
        
        from PyQt6.QtWidgets import QMessageBox
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to delete this extract?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Delete extract
            extract_id = self.current_extract.id
            self.db_session.delete(self.current_extract)
            self.db_session.commit()
            
            # Clear current extract
            self.current_extract = None
            
            # Reload extracts
            self._load_extracts()
            
            # Emit signal
            self.extractDeleted.emit()
            
            # Update status
            self.status_label.setText(f"Extract {extract_id} deleted")
    
    @pyqtSlot()
    def _on_copy_content(self):
        """Handle copy content action."""
        if not self.current_extract:
            return
        
        # Copy content to clipboard
        QApplication.clipboard().setText(self.current_extract.content)
        
        # Update status
        self.status_label.setText("Extract content copied to clipboard")
    
    @pyqtSlot()
    def _on_filter_changed(self):
        """Handle filter change."""
        # Check if processed and unprocessed checkboxes are both unchecked
        if not self.processed_checkbox.isChecked() and not self.unprocessed_checkbox.isChecked():
            # Force one of them to be checked (processed by default)
            self.processed_checkbox.setChecked(True)
        
        # Reload extracts
        self._load_extracts()
    
    @pyqtSlot()
    def _on_refresh(self):
        """Handle refresh button click."""
        # Reload data
        self._populate_documents()
        self._populate_tags()
        self._populate_categories()
        self._load_extracts()
        
        # Update status
        self.status_label.setText("Data refreshed")
    
    @pyqtSlot(QModelIndex)
    def _on_extract_double_clicked(self, index):
        """Handle extract double-click."""
        if not index.isValid():
            return
        
        # Get extract ID
        row = index.row()
        extract_id = self.extracts_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # Emit signal
        self.extractSelected.emit(extract_id)
