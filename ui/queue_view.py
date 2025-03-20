# ui/queue_view.py

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QComboBox, QFormLayout, QSpinBox, QSplitter,
    QMessageBox, QMenu, QCheckBox, QTabWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QModelIndex
from PyQt6.QtGui import QIcon, QAction, QColor, QBrush, QKeySequence, QShortcut

from core.knowledge_base.models import Document, Category
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
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(6)
        self.queue_table.setHorizontalHeaderLabels(["Title", "Category", "Priority", "Reading Count", "Last Read", "Next Due"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.queue_table.doubleClicked.connect(self._on_document_selected)
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
            if self.queue_table.rowCount() > 0:
                self.queue_table.selectRow(0)
                first_doc_id = self.queue_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
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
    
    def _populate_queue_table(self, doc_by_date: Dict[str, List[Document]]):
        """Populate the queue table with documents."""
        self.queue_table.setRowCount(0)  # Clear table
        
        row = 0
        
        # Add overdue documents first with red highlight
        if "Overdue" in doc_by_date:
            for doc in doc_by_date["Overdue"]:
                self._add_document_to_queue(doc, row, QColor(255, 200, 200))
                row += 1
        
        # Add documents due by date
        for date_str, docs in doc_by_date.items():
            if date_str not in ["Overdue", "New"]:  # Skip special categories
                for doc in docs:
                    self._add_document_to_queue(doc, row)
                    row += 1
        
        # Add new documents last with blue highlight
        if "New" in doc_by_date:
            for doc in doc_by_date["New"]:
                self._add_document_to_queue(doc, row, QColor(200, 220, 255))
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
            if self.queue_table.rowCount() > 0:
                self.queue_table.selectRow(0)
                
        except Exception as e:
            logger.exception(f"Error ensuring queue order: {e}")
    
    def _add_document_to_queue(self, doc: Document, row: int, background_color=None):
        """Add a document to the queue table."""
        self.queue_table.insertRow(row)
        
        # Title
        title_item = QTableWidgetItem(doc.title)
        title_item.setData(Qt.ItemDataRole.UserRole, doc.id)
        if background_color:
            title_item.setBackground(QBrush(background_color))
        self.queue_table.setItem(row, 0, title_item)
        
        # Category
        category_name = doc.category.name if doc.category else "Uncategorized"
        category_item = QTableWidgetItem(category_name)
        if background_color:
            category_item.setBackground(QBrush(background_color))
        self.queue_table.setItem(row, 1, category_item)
        
        # Priority
        priority_item = QTableWidgetItem(str(doc.priority))
        if background_color:
            priority_item.setBackground(QBrush(background_color))
        self.queue_table.setItem(row, 2, priority_item)
        
        # Reading count
        count_item = QTableWidgetItem(str(doc.reading_count or 0))
        if background_color:
            count_item.setBackground(QBrush(background_color))
        self.queue_table.setItem(row, 3, count_item)
        
        # Last read
        last_read = doc.last_reading_date.strftime("%Y-%m-%d") if doc.last_reading_date else "Never"
        last_read_item = QTableWidgetItem(last_read)
        if background_color:
            last_read_item.setBackground(QBrush(background_color))
        self.queue_table.setItem(row, 4, last_read_item)
        
        # Next due
        next_due = doc.next_reading_date.strftime("%Y-%m-%d") if doc.next_reading_date else "New"
        next_due_item = QTableWidgetItem(next_due)
        if background_color:
            next_due_item.setBackground(QBrush(background_color))
        self.queue_table.setItem(row, 5, next_due_item)
    
    def _populate_calendar_view(self, doc_by_date: Dict[str, List[Document]]):
        """Populate the calendar view with documents grouped by date."""
        # Clear existing calendar view
        for i in reversed(range(self.queue_tabs.widget(1).layout().count())):
            widget = self.queue_tabs.widget(1).layout().itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        self.date_tables = {}
        
        # Add overdue documents
        if "Overdue" in doc_by_date and doc_by_date["Overdue"]:
            overdue_group = QGroupBox("Overdue Documents")
            overdue_layout = QVBoxLayout(overdue_group)
            
            overdue_table = QTableWidget()
            overdue_table.setColumnCount(4)
            overdue_table.setHorizontalHeaderLabels(["Title", "Category", "Priority", "Due Date"])
            overdue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            overdue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            overdue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            overdue_table.doubleClicked.connect(self._on_document_selected)
            
            for i, doc in enumerate(doc_by_date["Overdue"]):
                overdue_table.insertRow(i)
                
                # Title
                title_item = QTableWidgetItem(doc.title)
                title_item.setData(Qt.ItemDataRole.UserRole, doc.id)
                title_item.setBackground(QBrush(QColor(255, 200, 200)))  # light red
                overdue_table.setItem(i, 0, title_item)
                
                # Category
                category_name = doc.category.name if doc.category else "Uncategorized"
                category_item = QTableWidgetItem(category_name)
                category_item.setBackground(QBrush(QColor(255, 200, 200)))
                overdue_table.setItem(i, 1, category_item)
                
                # Priority
                priority_item = QTableWidgetItem(str(doc.priority))
                priority_item.setBackground(QBrush(QColor(255, 200, 200)))
                overdue_table.setItem(i, 2, priority_item)
                
                # Due Date
                due_date = doc.next_reading_date.strftime("%Y-%m-%d") if doc.next_reading_date else "New"
                due_item = QTableWidgetItem(due_date)
                due_item.setBackground(QBrush(QColor(255, 200, 200)))
                overdue_table.setItem(i, 3, due_item)
            
            overdue_layout.addWidget(overdue_table)
            self.queue_tabs.widget(1).layout().addWidget(overdue_group)
            self.date_tables["Overdue"] = overdue_table
        
        # Add documents due by date
        for date_str, docs in doc_by_date.items():
            if date_str not in ["Overdue", "New"] and docs:  # Skip special categories and empty dates
                date_group = QGroupBox(f"Due on {date_str}")
                date_layout = QVBoxLayout(date_group)
                
                date_table = QTableWidget()
                date_table.setColumnCount(3)
                date_table.setHorizontalHeaderLabels(["Title", "Category", "Priority"])
                date_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                date_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
                date_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                date_table.doubleClicked.connect(self._on_document_selected)
                
                for i, doc in enumerate(docs):
                    date_table.insertRow(i)
                    
                    # Title
                    title_item = QTableWidgetItem(doc.title)
                    title_item.setData(Qt.ItemDataRole.UserRole, doc.id)
                    date_table.setItem(i, 0, title_item)
                    
                    # Category
                    category_name = doc.category.name if doc.category else "Uncategorized"
                    date_table.setItem(i, 1, QTableWidgetItem(category_name))
                    
                    # Priority
                    date_table.setItem(i, 2, QTableWidgetItem(str(doc.priority)))
                
                date_layout.addWidget(date_table)
                self.queue_tabs.widget(1).layout().addWidget(date_group)
                self.date_tables[date_str] = date_table
        
        # Add new documents
        if "New" in doc_by_date and doc_by_date["New"]:
            new_group = QGroupBox("New Documents")
            new_layout = QVBoxLayout(new_group)
            
            new_table = QTableWidget()
            new_table.setColumnCount(3)
            new_table.setHorizontalHeaderLabels(["Title", "Category", "Priority"])
            new_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            new_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            new_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            new_table.doubleClicked.connect(self._on_document_selected)
            
            for i, doc in enumerate(doc_by_date["New"]):
                new_table.insertRow(i)
                
                # Title
                title_item = QTableWidgetItem(doc.title)
                title_item.setData(Qt.ItemDataRole.UserRole, doc.id)
                title_item.setBackground(QBrush(QColor(200, 220, 255)))  # light blue
                new_table.setItem(i, 0, title_item)
                
                # Category
                category_name = doc.category.name if doc.category else "Uncategorized"
                category_item = QTableWidgetItem(category_name)
                category_item.setBackground(QBrush(QColor(200, 220, 255)))
                new_table.setItem(i, 1, category_item)
                
                # Priority
                priority_item = QTableWidgetItem(str(doc.priority))
                priority_item.setBackground(QBrush(QColor(200, 220, 255)))
                new_table.setItem(i, 2, priority_item)
            
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
        """Open the next document for reading."""
        try:
            # If there are no documents in the queue table, use the FSRS algorithm
            if self.queue_table.rowCount() == 0:
                next_docs = self.fsrs.get_next_documents(count=1)
                
                if not next_docs:
                    QMessageBox.information(
                        self, "No Documents", 
                        "There are no documents in the queue."
                    )
                    return
                
                # Get the document
                doc = next_docs[0]
                
                # Emit signal to open the document
                self.documentSelected.emit(doc.id)
                
                # Update UI to reflect selection
                self.set_current_document(doc.id)
                return
            
            # If there are documents in the queue table, use the queue order
            current_row = -1
            current_doc_id = self._get_current_document_id()
            
            if current_doc_id:
                # Find the current document in the queue table
                for row in range(self.queue_table.rowCount()):
                    doc_id = self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                    if doc_id == current_doc_id:
                        current_row = row
                        break
            
            # Move to the next document in the queue
            next_row = current_row + 1
            if next_row >= self.queue_table.rowCount():
                next_row = 0  # Wrap around to the beginning
            
            next_doc_id = self.queue_table.item(next_row, 0).data(Qt.ItemDataRole.UserRole)
            self.documentSelected.emit(next_doc_id)
            self.set_current_document(next_doc_id)
            
            # Update UI to reflect selection
            self.queue_table.selectRow(next_row)
            
        except Exception as e:
            logger.exception(f"Error getting next document: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error opening next document: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_read_prev(self):
        """Handle previous document button click."""
        # Find current document in the queue
        current_row = -1
        current_doc_id = self._get_current_document_id()
        
        if current_doc_id:
            # Try to find the document in the queue table
            for row in range(self.queue_table.rowCount()):
                doc_id = self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if doc_id == current_doc_id:
                    current_row = row
                    break
            
            # If found, get the previous document
            if current_row > 0:
                prev_doc_id = self.queue_table.item(current_row - 1, 0).data(Qt.ItemDataRole.UserRole)
                self.documentSelected.emit(prev_doc_id)
                return
        
        # If no current document or it's the first one, get the last document in the queue
        if self.queue_table.rowCount() > 0:
            last_row = self.queue_table.rowCount() - 1
            last_doc_id = self.queue_table.item(last_row, 0).data(Qt.ItemDataRole.UserRole)
            self.documentSelected.emit(last_doc_id)
        else:
            QMessageBox.information(
                self, "No Documents", 
                "There are no documents in the queue matching your filters."
            )
    
    def _get_current_document_id(self):
        """Get the ID of the currently open document."""
        # This method will be connected to the main window to get the current document ID
        return getattr(self, '_current_document_id', None)
    
    def set_current_document(self, doc_id):
        """Set the current document ID for navigation purposes."""
        self._current_document_id = doc_id
        
        # Update button states based on queue position
        self._update_navigation_buttons()
    
    def _update_navigation_buttons(self):
        """Update the enabled state of navigation buttons."""
        has_docs = self.queue_table.rowCount() > 0
        
        self.read_next_button.setEnabled(has_docs)
        self.prev_button.setEnabled(has_docs)
    
    @pyqtSlot(QPoint)
    def _on_queue_context_menu(self, pos):
        """Show context menu for queue table."""
        index = self.queue_table.indexAt(pos)
        if not index.isValid():
            return
        
        # Get document ID
        row = index.row()
        doc_id = self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # Create menu
        menu = QMenu(self)
        
        # Add actions
        open_action = menu.addAction("Open Document")
        open_action.triggered.connect(lambda: self.documentSelected.emit(doc_id))
        
        menu.addSeparator()
        
        # Priority submenu
        priority_menu = menu.addMenu("Set Priority")
        
        priorities = [1, 25, 50, 75, 100]
        for p in priorities:
            priority_action = priority_menu.addAction(f"{p}")
            priority_action.triggered.connect(lambda checked, p=p: self._on_set_priority(doc_id, p))
        
        menu.addSeparator()
        
        # Rating actions - these will reschedule the document
        rate_menu = menu.addMenu("Rate Document")
        
        ratings = [
            ("Hard/Forgot (1)", 1),
            ("Difficult (2)", 2),
            ("Good (3)", 3),
            ("Easy (4)", 4),
            ("Very Easy (5)", 5)
        ]
        
        for label, rating in ratings:
            rate_action = rate_menu.addAction(label)
            rate_action.triggered.connect(lambda checked, r=rating: self._on_rate_document(doc_id, r))
            
        menu.addSeparator()
        
        # Delete action
        delete_action = menu.addAction("Delete Document")
        delete_action.triggered.connect(lambda: self._on_delete_document(doc_id))
        
        # Show menu
        menu.exec(self.queue_table.viewport().mapToGlobal(pos))
    
    @pyqtSlot(QModelIndex)
    def _on_document_selected(self, index):
        """Handle document selection from tables."""
        # This works for both the main queue table and date tables
        item = self.sender().item(index.row(), 0)
        if item:
            doc_id = item.data(Qt.ItemDataRole.UserRole)
            if doc_id:
                self.documentSelected.emit(doc_id)
    
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
