# ui/queue_view.py

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QComboBox, QFormLayout, QSpinBox, QSplitter,
    QMessageBox, QMenu, QCheckBox, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QModelIndex
from PyQt6.QtGui import QIcon, QAction, QColor, QBrush, QKeySequence, QShortcut, QPalette

from core.knowledge_base.models import Document, Category, Extract
from core.spaced_repetition import FSRSAlgorithm
from core.utils.settings_manager import SettingsManager
from core.utils.shortcuts import ShortcutManager

logger = logging.getLogger(__name__)

class QueueView(QWidget):
    """Widget for managing the document reading queue."""
    
    documentSelected = pyqtSignal(int)  # document_id
    
    def __init__(self, db_session, settings_manager=None):
        super().__init__()
        
        self.db_session = db_session
        self.settings_manager = settings_manager or SettingsManager()
        
        # Initialize FSRS with algorithm settings from the settings manager
        fsrs_params = self._get_fsrs_params()
        self.fsrs = FSRSAlgorithm(db_session, params=fsrs_params)
        
        # Create UI
        self._create_ui()
        
        # Set up keyboard shortcuts
        self._setup_shortcuts()
        
        # Load initial data
        self._load_queue_data()
    
    def _get_fsrs_params(self) -> Dict[str, Any]:
        """Get FSRS algorithm parameters from settings."""
        if not self.settings_manager:
            return None
            
        # Get algorithm settings
        min_interval = self.settings_manager.get_setting("algorithm", "minimum_interval", 1)
        max_interval = self.settings_manager.get_setting("algorithm", "maximum_interval", 3650)
        interval_modifier = self.settings_manager.get_setting("algorithm", "interval_modifier", 1.0)
        target_retention = self.settings_manager.get_setting("algorithm", "target_retention", 0.9)
        
        # Create params dictionary with only the settings that should override defaults
        params = {
            "MIN_INTERVAL": min_interval,
            "MAX_INTERVAL": max_interval,
            "R_TARGET": target_retention,
        }
        
        return params
    
    def _setup_shortcuts(self):
        """Set up keyboard shortcuts for queue operations."""
        # Navigation shortcuts
        self.shortcut_next = QShortcut(ShortcutManager.QUEUE_NEXT, self)
        self.shortcut_next.activated.connect(self._on_read_next)
        
        self.shortcut_prev = QShortcut(ShortcutManager.QUEUE_PREV, self)
        self.shortcut_prev.activated.connect(self._on_read_prev)
        
        # Rating shortcuts
        self.shortcut_rate_1 = QShortcut(ShortcutManager.QUEUE_RATE_1, self)
        self.shortcut_rate_1.activated.connect(lambda: self._rate_current_document(1))
        
        self.shortcut_rate_2 = QShortcut(ShortcutManager.QUEUE_RATE_2, self)
        self.shortcut_rate_2.activated.connect(lambda: self._rate_current_document(2))
        
        self.shortcut_rate_3 = QShortcut(ShortcutManager.QUEUE_RATE_3, self)
        self.shortcut_rate_3.activated.connect(lambda: self._rate_current_document(3))
        
        self.shortcut_rate_4 = QShortcut(ShortcutManager.QUEUE_RATE_4, self)
        self.shortcut_rate_4.activated.connect(lambda: self._rate_current_document(4))
        
        self.shortcut_rate_5 = QShortcut(ShortcutManager.QUEUE_RATE_5, self)
        self.shortcut_rate_5.activated.connect(lambda: self._rate_current_document(5))
    
    def _rate_current_document(self, rating: int):
        """Rate the currently selected document."""
        doc_id = self._get_current_document_id()
        if doc_id:
            try:
                self._on_rate_document(doc_id, rating)
            except Exception as e:
                logger.exception(f"Error rating document: {e}")
                QMessageBox.warning(
                    self, "Error", 
                    f"Error rating document: {str(e)}"
                )
        else:
            # Optionally provide feedback that no document is currently selected
            self.refresh_button.setFocus()  # Set focus to a UI element to indicate that the shortcut was received
            
    def keyPressEvent(self, event):
        """Handle keyboard events for queue navigation and rating."""
        key = event.key()
        
        # Check for digit keys 1-5 for ratings (alternative to shortcuts)
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_5:
            rating = key - Qt.Key.Key_0  # Convert key code to number (1-5)
            self._rate_current_document(rating)
            event.accept()
            return
            
        # Check for N/P keys for navigation (alternative to shortcuts)
        elif key == Qt.Key.Key_N:
            self._on_read_next()
            event.accept()
            return
        elif key == Qt.Key.Key_P:
            self._on_read_prev()
            event.accept()
            return
            
        # Pass event to parent for default handling
        super().keyPressEvent(event)
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Controls section
        controls_group = QGroupBox("Queue Controls")
        controls_layout = QHBoxLayout(controls_group)
        
        # Category filter
        filter_layout = QFormLayout()
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        self._populate_categories()
        self.category_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addRow("Category:", self.category_combo)
        
        # Days ahead filter
        self.days_ahead_spin = QSpinBox()
        self.days_ahead_spin.setRange(1, 30)
        self.days_ahead_spin.setValue(7)
        self.days_ahead_spin.valueChanged.connect(self._on_filter_changed)
        filter_layout.addRow("Days ahead:", self.days_ahead_spin)
        
        # Include new documents
        self.include_new_check = QCheckBox("Include new documents")
        self.include_new_check.setChecked(True)
        self.include_new_check.stateChanged.connect(self._on_filter_changed)
        filter_layout.addRow("", self.include_new_check)
        
        controls_layout.addLayout(filter_layout)
        
        # Action buttons
        buttons_layout = QVBoxLayout()
        
        self.refresh_button = QPushButton("Refresh Queue")
        self.refresh_button.clicked.connect(self._on_refresh)
        buttons_layout.addWidget(self.refresh_button)
        
        # Add navigation buttons in a horizontal layout
        nav_buttons_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("Previous Document (P)")
        self.prev_button.clicked.connect(self._on_read_prev)
        self.prev_button.setToolTip("Open the previous document in the queue (Shortcut: P)")
        nav_buttons_layout.addWidget(self.prev_button)
        
        self.read_next_button = QPushButton("Next Document (N)")
        self.read_next_button.clicked.connect(self._on_read_next)
        self.read_next_button.setToolTip("Open the next document in the queue (Shortcut: N)")
        nav_buttons_layout.addWidget(self.read_next_button)
        
        buttons_layout.addLayout(nav_buttons_layout)
        
        # Add keyboard shortcuts hint
        shortcut_label = QLabel("Rating shortcuts: 1=Hard, 2=Difficult, 3=Good, 4=Easy, 5=Very Easy")
        shortcut_label.setStyleSheet("color: #666; font-style: italic;")
        buttons_layout.addWidget(shortcut_label)
        
        controls_layout.addLayout(buttons_layout)
        
        # Stats layout
        stats_layout = QFormLayout()
        
        self.total_label = QLabel("0")
        stats_layout.addRow("Total documents:", self.total_label)
        
        self.due_today_label = QLabel("0")
        stats_layout.addRow("Due today:", self.due_today_label)
        
        self.due_week_label = QLabel("0")
        stats_layout.addRow("Due this week:", self.due_week_label)
        
        self.overdue_label = QLabel("0")
        stats_layout.addRow("Overdue:", self.overdue_label)
        
        self.new_label = QLabel("0")
        stats_layout.addRow("New documents:", self.new_label)
        
        controls_layout.addLayout(stats_layout)
        
        main_layout.addWidget(controls_group)
        
        # Queue tabs
        self.queue_tabs = QTabWidget()
        
        # Create tabs
        self._create_queue_tab()
        self._create_calendar_tab()
        
        main_layout.addWidget(self.queue_tabs)
    
    def _create_queue_tab(self):
        """Create the main queue tab with document list."""
        queue_tab = QWidget()
        queue_layout = QVBoxLayout(queue_tab)
        
        # Queue table
        self.queue_table = QTreeWidget()
        self.queue_table.setColumnCount(6)
        self.queue_table.setHeaderLabels(["Title", "Category", "Priority", "Reading Count", "Last Read", "Next Due"])
        self.queue_table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.header().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.queue_table.itemDoubleClicked.connect(lambda item, column: self._on_tree_item_selected(item, column))
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self._on_queue_context_menu)
        
        queue_layout.addWidget(self.queue_table)
        
        self.queue_tabs.addTab(queue_tab, "Queue List")
    
    def _create_calendar_tab(self):
        """Create the calendar view tab showing documents by due date."""
        calendar_tab = QWidget()
        calendar_layout = QVBoxLayout(calendar_tab)
        
        # Scrollable table area
        table_layout = QVBoxLayout()
        
        # This will be populated dynamically with document groups by date
        self.date_tables = {}
        
        # We'll create individual QTableWidgets for each date in _load_queue_data
        
        calendar_layout.addLayout(table_layout)
        
        self.queue_tabs.addTab(calendar_tab, "Calendar View")
    
    def _populate_categories(self):
        """Populate the category selector."""
        categories = self.db_session.query(Category).all()
        
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
    
    def _load_queue_data(self):
        """Load queue data based on current filters."""
        try:
            # Get filter parameters
            category_id = self.category_combo.currentData()
            days_ahead = self.days_ahead_spin.value()
            include_new = self.include_new_check.isChecked()
            
            # Update stats display - we need to implement this with FSRS
            self._update_queue_stats()
            
            # Load documents by due date
            doc_by_date = self._get_documents_by_due_date(
                days=days_ahead,
                category_id=category_id,
                include_new=include_new
            )
            
            # Populate queue table
            self._populate_queue_table(doc_by_date)
            
            # Populate calendar view
            self._populate_calendar_view(doc_by_date)
            
            # If there are documents in the queue, select the first one
            if self.queue_table.topLevelItemCount() > 0:
                self.queue_table.topLevelItem(0).setSelected(True)
                first_doc_id = self.queue_table.topLevelItem(0).text(0)
                self.set_current_document(first_doc_id)
            
        except Exception as e:
            logger.exception(f"Error loading queue data: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error loading queue data: {str(e)}"
            )
    
    def _update_queue_stats(self):
        """Update the queue statistics using FSRS."""
        # Count total documents
        total_docs = self.db_session.query(Document).count()
        
        # Count documents due today
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        
        due_today = self.db_session.query(Document).filter(
            Document.next_reading_date.between(today_start, today_end)
        ).count()
        
        # Count documents due in the next 7 days
        next_week = today_start + timedelta(days=7)
        
        due_this_week = self.db_session.query(Document).filter(
            Document.next_reading_date.between(today_start, next_week)
        ).count()
        
        # Count new documents (never read)
        new_documents = self.db_session.query(Document).filter(
            Document.next_reading_date == None
        ).count()
        
        # Count overdue documents (due date in the past)
        overdue = self.db_session.query(Document).filter(
            Document.next_reading_date < today_start
        ).count()
        
        # Update stats display
        self.total_label.setText(str(total_docs))
        self.due_today_label.setText(str(due_today))
        self.due_week_label.setText(str(due_this_week))
        self.overdue_label.setText(str(overdue))
        self.new_label.setText(str(new_documents))
    
    def _get_documents_by_due_date(self, days: int = 7, 
                                   category_id: Optional[int] = None,
                                   include_new: bool = True) -> Dict[str, List[Document]]:
        """
        Get documents grouped by due date.
        
        Args:
            days: Number of days to look ahead
            category_id: Optional category filter
            include_new: Whether to include new documents
            
        Returns:
            Dictionary mapping date strings to lists of documents
        """
        result = {}
        
        # Base query
        query = self.db_session.query(Document)
        
        # Apply category filter if specified
        if category_id is not None:
            query = query.filter(Document.category_id == category_id)
        
        # Add "Overdue" category
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        overdue_docs = query.filter(Document.next_reading_date < today).order_by(
            Document.priority.desc(),
            Document.next_reading_date.asc()
        ).all()
        
        if overdue_docs:
            result["Overdue"] = overdue_docs
        
        # Add documents by due date
        for i in range(days):
            date = today + timedelta(days=i)
            date_end = date + timedelta(days=1)
            date_str = date.strftime("%Y-%m-%d")
            
            # Get documents due on this date
            date_docs = query.filter(
                Document.next_reading_date.between(date, date_end)
            ).order_by(
                Document.priority.desc()
            ).all()
            
            if date_docs:
                result[date_str] = date_docs
        
        # Add "New" category (documents never reviewed)
        if include_new:
            new_docs = query.filter(Document.next_reading_date == None).order_by(
                Document.priority.desc(),
                Document.imported_date.desc()
            ).all()
            
            if new_docs:
                result["New"] = new_docs
        
        return result
    
    def _get_theme_colors(self):
        """Get appropriate colors for the current theme."""
        # Check if we're in dark mode by examining the application's palette
        app = QApplication.instance()
        if app:
            palette = app.palette()
            # If text color is light, we're likely in dark mode
            is_dark_mode = palette.color(QPalette.ColorRole.WindowText).lightness() > 128
        else:
            is_dark_mode = False

        if is_dark_mode:
            # Dark theme colors (more subdued and visible on dark backgrounds)
            return {
                'overdue': QColor(120, 50, 50),  # Darker red
                'new': QColor(40, 70, 120),      # Darker blue
                'extract': QColor(70, 70, 70),   # Dark gray
                'extract_child': QColor(60, 60, 60)  # Slightly darker gray
            }
        else:
            # Light theme colors (original colors)
            return {
                'overdue': QColor(255, 200, 200),  # Light red
                'new': QColor(200, 220, 255),      # Light blue
                'extract': QColor(240, 240, 240),  # Light gray
                'extract_child': QColor(245, 245, 245)  # Very light gray
            }
    
    def _populate_queue_table(self, doc_by_date: Dict[str, List[Document]]):
        """Populate the queue table with documents."""
        self.queue_table.clear()
        
        row = 0
        theme_colors = self._get_theme_colors()
        
        # Add overdue documents first with highlight
        if "Overdue" in doc_by_date:
            for doc in doc_by_date["Overdue"]:
                self._add_document_to_queue(doc, row, theme_colors['overdue'])
                row += 1
        
        # Add documents due by date
        for date_str, docs in doc_by_date.items():
            if date_str not in ["Overdue", "New"]:  # Skip special categories
                for doc in docs:
                    self._add_document_to_queue(doc, row)
                    row += 1
        
        # Add new documents last with highlight
        if "New" in doc_by_date:
            for doc in doc_by_date["New"]:
                self._add_document_to_queue(doc, row, theme_colors['new'])
                row += 1
                
        # Ensure the table is sorted by priority and due date within each group
        self._ensure_queue_order()
    
    def _ensure_queue_order(self):
        """
        Sort the queue table to maintain proper order by priority and due date.
        This ensures "Next Document" navigation follows the proper order.
        """
        try:
            # The queue ordering is already handled correctly by _get_documents_by_due_date
            # This method is a hook for future customization
            
            # If needed in the future, we could implement custom sorting here
            # For now, we rely on the order from _get_documents_by_due_date
            
            # Update selection and navigation buttons
            self._update_navigation_buttons()
            
            # If there are documents in the queue, select the first row by default
            if self.queue_table.topLevelItemCount() > 0:
                self.queue_table.topLevelItem(0).setSelected(True)
                
        except Exception as e:
            logger.exception(f"Error ensuring queue order: {e}")
    
    def _add_document_to_queue(self, doc: Document, row: int, background_color=None):
        """Add a document to the queue table."""
        item = QTreeWidgetItem()
        item.setText(0, doc.title)
        item.setText(1, doc.category.name if doc.category else "Uncategorized")
        item.setText(2, str(doc.priority))
        item.setText(3, str(doc.reading_count or 0))
        item.setText(4, doc.last_reading_date.strftime("%Y-%m-%d") if doc.last_reading_date else "Never")
        item.setText(5, doc.next_reading_date.strftime("%Y-%m-%d") if doc.next_reading_date else "New")
        # Store document ID as data
        item.setData(0, Qt.ItemDataRole.UserRole, doc.id)
        if background_color:
            # Apply background color to all columns
            for col in range(6):
                item.setBackground(col, QBrush(background_color))
        
        # Add extracts as child items
        self._add_extracts_to_document(doc, item)
        
        self.queue_table.insertTopLevelItem(row, item)
    
    def _add_extracts_to_document(self, doc: Document, parent_item: QTreeWidgetItem):
        """Add extracts as child items under the document."""
        # Get extracts for this document
        extracts = self.db_session.query(Extract).filter(Extract.document_id == doc.id).all()
        theme_colors = self._get_theme_colors()
        
        for extract in extracts:
            extract_item = QTreeWidgetItem(parent_item)
            # Use a shorter preview of the content for the title column
            content_preview = extract.content[:80] + "..." if len(extract.content) > 80 else extract.content
            extract_item.setText(0, content_preview)
            
            # Set other columns
            extract_item.setText(1, "") # No category for extracts
            extract_item.setText(2, str(extract.priority) if extract.priority else "")
            extract_item.setText(3, "") # No reading count for extracts
            extract_item.setText(4, extract.last_reviewed.strftime("%Y-%m-%d") if extract.last_reviewed else "")
            extract_item.setText(5, "") # No next due for extracts
            
            # Store extract ID as data with a different role to distinguish from document IDs
            extract_item.setData(0, Qt.ItemDataRole.UserRole, extract.id)
            extract_item.setData(0, Qt.ItemDataRole.UserRole+1, "extract") # Type marker
            
            # Use a different background color for extract items - apply to all columns
            for col in range(6):
                extract_item.setBackground(col, QBrush(theme_colors['extract']))
            
            # Add any child extracts if this is a hierarchical extract
            if extract.children:
                for child_extract in extract.children:
                    child_item = QTreeWidgetItem(extract_item)
                    child_content_preview = child_extract.content[:80] + "..." if len(child_extract.content) > 80 else child_extract.content
                    child_item.setText(0, child_content_preview)
                    child_item.setData(0, Qt.ItemDataRole.UserRole, child_extract.id)
                    child_item.setData(0, Qt.ItemDataRole.UserRole+1, "extract")
                    # Apply to all columns
                    for col in range(6):
                        child_item.setBackground(col, QBrush(theme_colors['extract_child']))
    
    def _populate_calendar_view(self, doc_by_date: Dict[str, List[Document]]):
        """Populate the calendar view with documents grouped by date."""
        # Clear existing calendar view
        for i in reversed(range(self.queue_tabs.widget(1).layout().count())):
            widget = self.queue_tabs.widget(1).layout().itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        self.date_tables = {}
        theme_colors = self._get_theme_colors()
        
        # Add overdue documents
        if "Overdue" in doc_by_date and doc_by_date["Overdue"]:
            overdue_group = QGroupBox("Overdue Documents")
            overdue_layout = QVBoxLayout(overdue_group)
            
            overdue_table = QTreeWidget()
            overdue_table.setColumnCount(4)
            overdue_table.setHeaderLabels(["Title", "Category", "Priority", "Due Date"])
            overdue_table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            overdue_table.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
            overdue_table.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
            overdue_table.itemDoubleClicked.connect(lambda item, column: self._on_tree_item_selected(item, column))
            
            for i, doc in enumerate(doc_by_date["Overdue"]):
                item = QTreeWidgetItem([doc.title, doc.category.name if doc.category else "Uncategorized", str(doc.priority), doc.next_reading_date.strftime("%Y-%m-%d") if doc.next_reading_date else "New"])
                # Apply background color to all columns
                for col in range(4):
                    item.setBackground(col, QBrush(theme_colors['overdue']))
                overdue_table.insertTopLevelItem(i, item)
            
            overdue_layout.addWidget(overdue_table)
            self.queue_tabs.widget(1).layout().addWidget(overdue_group)
            self.date_tables["Overdue"] = overdue_table
        
        # Add documents due by date
        for date_str, docs in doc_by_date.items():
            if date_str not in ["Overdue", "New"] and docs:  # Skip special categories and empty dates
                date_group = QGroupBox(f"Due on {date_str}")
                date_layout = QVBoxLayout(date_group)
                
                date_table = QTreeWidget()
                date_table.setColumnCount(3)
                date_table.setHeaderLabels(["Title", "Category", "Priority"])
                date_table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                date_table.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
                date_table.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
                date_table.itemDoubleClicked.connect(lambda item, column: self._on_tree_item_selected(item, column))
                
                for i, doc in enumerate(docs):
                    item = QTreeWidgetItem([doc.title, doc.category.name if doc.category else "Uncategorized", str(doc.priority)])
                    date_table.insertTopLevelItem(i, item)
                
                date_layout.addWidget(date_table)
                self.queue_tabs.widget(1).layout().addWidget(date_group)
                self.date_tables[date_str] = date_table
        
        # Add new documents
        if "New" in doc_by_date and doc_by_date["New"]:
            new_group = QGroupBox("New Documents")
            new_layout = QVBoxLayout(new_group)
            
            new_table = QTreeWidget()
            new_table.setColumnCount(3)
            new_table.setHeaderLabels(["Title", "Category", "Priority"])
            new_table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            new_table.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
            new_table.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
            new_table.itemDoubleClicked.connect(lambda item, column: self._on_tree_item_selected(item, column))
            
            for i, doc in enumerate(doc_by_date["New"]):
                item = QTreeWidgetItem([doc.title, doc.category.name if doc.category else "Uncategorized", str(doc.priority)])
                # Apply background color to all columns
                for col in range(3):
                    item.setBackground(col, QBrush(theme_colors['new']))
                new_table.insertTopLevelItem(i, item)
            
            new_layout.addWidget(new_table)
            self.queue_tabs.widget(1).layout().addWidget(new_group)
            self.date_tables["New"] = new_table
    
    @pyqtSlot()
    def _on_filter_changed(self):
        """Handle filter changes."""
        self._load_queue_data()
    
    @pyqtSlot()
    def _on_refresh(self):
        """Handle refresh button click."""
        self._load_queue_data()
    
    @pyqtSlot()
    def _on_read_next(self):
        """Navigate to the next document in the queue."""
        try:
            # Get the current document ID
            current_doc_id = self._get_current_document_id()
            current_row = -1
            
            if current_doc_id:
                # Find the current document in the queue table
                for row in range(self.queue_table.topLevelItemCount()):
                    item = self.queue_table.topLevelItem(row)
                    if item.data(0, Qt.ItemDataRole.UserRole) == current_doc_id:
                        current_row = row
                        break
            
            # If the current document isn't found, start from the beginning
            if current_row == -1:
                # If there are no documents in the queue table, use the FSRS algorithm
                if self.queue_table.topLevelItemCount() == 0:
                    next_docs = self.fsrs.get_next_documents(count=1)
                    
                    if next_docs:
                        # Load the first document
                        self.documentSelected.emit(next_docs[0].id)
                        return
                    else:
                        # No documents available
                        QMessageBox.information(
                            self, "No Documents", 
                            "There are no documents in the queue."
                        )
                        return
                current_row = 0
            
            # Move to the next document in the queue
            next_row = current_row + 1
            if next_row >= self.queue_table.topLevelItemCount():
                next_row = 0  # Wrap around to the beginning
            
            next_doc_id = self.queue_table.topLevelItem(next_row).data(0, Qt.ItemDataRole.UserRole)
            self.documentSelected.emit(next_doc_id)
            self.set_current_document(next_doc_id)
            
        except Exception as e:
            logger.exception(f"Error navigating to next document: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error navigating to next document: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_read_prev(self):
        """Navigate to the previous document in the queue."""
        try:
            # Get the current document ID
            current_doc_id = self._get_current_document_id()
            current_row = -1
            
            if current_doc_id:
                # Try to find the document in the queue table
                for row in range(self.queue_table.topLevelItemCount()):
                    item = self.queue_table.topLevelItem(row)
                    if item.data(0, Qt.ItemDataRole.UserRole) == current_doc_id:
                        current_row = row
                        break
            
            # If found, get the previous document
            if current_row > 0:
                prev_row = current_row - 1
                prev_doc_id = self.queue_table.topLevelItem(prev_row).data(0, Qt.ItemDataRole.UserRole)
                self.documentSelected.emit(prev_doc_id)
                self.set_current_document(prev_doc_id)
                return
            
            # If no current document or it's the first one, get the last document in the queue
            if self.queue_table.topLevelItemCount() > 0:
                last_row = self.queue_table.topLevelItemCount() - 1
                last_doc_id = self.queue_table.topLevelItem(last_row).data(0, Qt.ItemDataRole.UserRole)
                self.documentSelected.emit(last_doc_id)
                self.set_current_document(last_doc_id)
            else:
                QMessageBox.information(
                    self, "No Documents", 
                    "There are no documents in the queue."
                )
                
        except Exception as e:
            logger.exception(f"Error navigating to previous document: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error navigating to previous document: {str(e)}"
            )
    
    def _get_current_document_id(self):
        """Get the ID of the currently selected document."""
        selected_items = self.queue_table.selectedItems()
        if not selected_items:
            return None
        
        item = selected_items[0]
        # Check if this is an extract
        item_type = item.data(0, Qt.ItemDataRole.UserRole+1)
        if item_type == "extract":
            # Get the parent document
            parent = item.parent()
            if parent:
                return parent.data(0, Qt.ItemDataRole.UserRole)
            return None
        
        # This is a document
        return item.data(0, Qt.ItemDataRole.UserRole)
    
    def set_current_document(self, doc_id):
        """Set the current document."""
        self._current_document_id = doc_id
        
        # Find and select the document in the tree
        for i in range(self.queue_table.topLevelItemCount()):
            item = self.queue_table.topLevelItem(i)
            if item.data(0, Qt.ItemDataRole.UserRole) == doc_id:
                # Select this item
                self.queue_table.clearSelection()
                item.setSelected(True)
                self.queue_table.scrollToItem(item)
                break
                
        # Update navigation buttons
        self._update_navigation_buttons()
    
    def _update_navigation_buttons(self):
        """Update the enabled state of navigation buttons."""
        has_docs = self.queue_table.topLevelItemCount() > 0
        
        self.read_next_button.setEnabled(has_docs)
        self.prev_button.setEnabled(has_docs)
    
    @pyqtSlot(QPoint)
    def _on_queue_context_menu(self, pos):
        """Show context menu for queue items."""
        # Get the item at the click position
        item = self.queue_table.itemAt(pos)
        if not item:
            return
        
        # Get item type and ID
        item_type = item.data(0, Qt.ItemDataRole.UserRole+1)
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        if not item_id:
            return
            
        # Create menu
        menu = QMenu(self)
        
        if item_type == "extract":
            # Context menu for extracts
            open_doc_action = menu.addAction("Open Document")
            open_doc_action.triggered.connect(lambda: self._handle_extract_selected(item_id))
            
            view_extract_action = menu.addAction("View Extract")
            view_extract_action.triggered.connect(lambda: self._view_extract(item_id))
            
            menu.addSeparator()
            
            # Priority submenu
            priority_menu = menu.addMenu("Set Priority")
            
            for priority in [25, 50, 75, 100]:
                priority_action = priority_menu.addAction(f"{priority}")
                priority_action.triggered.connect(
                    lambda checked, p=priority, i=item_id: self._on_set_extract_priority(i, p)
                )
                
        else:
            # Context menu for documents
            open_action = menu.addAction("Open Document")
            open_action.triggered.connect(lambda: self.documentSelected.emit(item_id))
            
            menu.addSeparator()
            
            # Priority submenu
            priority_menu = menu.addMenu("Set Priority")
            
            for priority in [25, 50, 75, 100]:
                priority_action = priority_menu.addAction(f"{priority}")
                priority_action.triggered.connect(
                    lambda checked, p=priority, i=item_id: self._on_set_priority(i, p)
                )
            
            # Rating submenu for documents only
            rating_menu = menu.addMenu("Rate")
            
            for rating in range(1, 6):
                rating_action = rating_menu.addAction(f"{rating} - {self._get_rating_label(rating)}")
                rating_action.triggered.connect(
                    lambda checked, r=rating, i=item_id: self._on_rate_document(i, r)
                )
            
            menu.addSeparator()
            
            delete_action = menu.addAction("Delete")
            delete_action.triggered.connect(lambda: self._on_delete_document(item_id))
        
        # Show menu
        menu.exec(self.queue_table.viewport().mapToGlobal(pos))
    
    @pyqtSlot(QModelIndex)
    def _on_tree_item_selected(self, item, column):
        """Handle item selection from tree."""
        # Check if this is an extract or a document
        item_type = item.data(0, Qt.ItemDataRole.UserRole+1)
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        if item_type == "extract":
            # This is an extract - handle extract selection
            self._handle_extract_selected(item_id)
        else:
            # This is a document - emit the signal
            self.documentSelected.emit(item_id)
    
    def _handle_extract_selected(self, extract_id):
        """Handle extract selection."""
        # Get the extract
        extract = self.db_session.query(Extract).filter(Extract.id == extract_id).first()
        if extract:
            # First, open the document that contains this extract
            self.documentSelected.emit(extract.document_id)
            
            # Here you could add code to scroll to the extract position in the document
            # This would depend on how your document viewer handles focusing on extracts
            
            # You could also emit a new signal specifically for extract selection
            # which would be connected to a handler in the main application
    
    def _on_set_priority(self, doc_id: int, priority: int):
        """Handle setting document priority."""
        if self.fsrs.update_document_priority(doc_id, priority):
            self._load_queue_data()
        else:
            QMessageBox.warning(
                self, "Error", 
                f"Failed to update document priority."
            )
    
    def _on_rate_document(self, doc_id: int, rating: int):
        """Rate a document and schedule it."""
        try:
            # Map rating from 1-5 scale to 1-4 FSRS scale
            fsrs_rating = 1  # Default to "Again"
            if rating == 1:  # Hard/Forgot
                fsrs_rating = 1  # Again
            elif rating == 2:  # Medium/Difficult
                fsrs_rating = 2  # Hard
            elif rating == 3:  # Good
                fsrs_rating = 3  # Good
            elif rating >= 4:  # Easy or Very Easy
                fsrs_rating = 4  # Easy
            
            # Schedule using FSRS
            result = self.fsrs.schedule_document(doc_id, fsrs_rating)
            
            if result:
                next_date = result['next_reading_date'].strftime("%Y-%m-%d")
                QMessageBox.information(
                    self, "Document Scheduled", 
                    f"Document scheduled for next review on {next_date} "
                    f"(in {result['interval_days']} days)."
                )
                
                # Refresh the queue
                self._load_queue_data()
            else:
                QMessageBox.warning(
                    self, "Error", 
                    "Failed to schedule document."
                )
                
        except Exception as e:
            logger.exception(f"Error rating document: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error rating document: {str(e)}"
            )

    def update_settings(self):
        """Update FSRS parameters from settings."""
        if not self.settings_manager:
            return
            
        # Get updated parameters
        fsrs_params = self._get_fsrs_params()
        
        # Update FSRS algorithm parameters
        self.fsrs.params.update(fsrs_params)
        
        # Reload queue data with new parameters
        self._load_queue_data()

    def _on_delete_document(self, doc_id: int):
        """Handle document deletion."""
        try:
            # Get document title for confirmation message
            document = self.db_session.query(Document).get(doc_id)
            if not document:
                QMessageBox.warning(self, "Error", "Document not found.")
                return
                
            # Show confirmation dialog
            reply = QMessageBox.question(
                self, 
                "Confirm Deletion",
                f"Are you sure you want to delete the document '{document.title}'?\n\nThis action cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Delete document
                self.db_session.delete(document)
                self.db_session.commit()
                
                # Show success message
                QMessageBox.information(self, "Success", f"Document '{document.title}' was deleted successfully.")
                
                # Refresh the queue
                self._load_queue_data()
                
        except Exception as e:
            logger.exception(f"Error deleting document: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error deleting document: {str(e)}"
            )
            # Rollback in case of error
            self.db_session.rollback()

    def _view_extract(self, extract_id):
        """View an extract in detail."""
        # This could open a dialog showing the full extract content
        extract = self.db_session.query(Extract).filter(Extract.id == extract_id).first()
        if extract:
            # Display a simple message box for now
            QMessageBox.information(
                self, 
                "Extract",
                f"<b>Content:</b><br>{extract.content}<br><br>"
                f"<b>Context:</b><br>{extract.context or 'No context'}"
            )
    
    def _on_set_extract_priority(self, extract_id, priority):
        """Set priority for an extract."""
        try:
            extract = self.db_session.query(Extract).filter(Extract.id == extract_id).first()
            if extract:
                extract.priority = priority
                self.db_session.commit()
                self._on_refresh()  # Refresh the display
        except Exception as e:
            logger.exception(f"Error setting extract priority: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error setting extract priority: {str(e)}"
            )
            
    def _get_rating_label(self, rating):
        """Get a text label for a numerical rating."""
        labels = {
            1: "Hard",
            2: "Difficult",
            3: "Good",
            4: "Easy",
            5: "Very Easy"
        }
        return labels.get(rating, "Unknown")
