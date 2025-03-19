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
from PyQt6.QtGui import QIcon, QAction, QColor, QBrush

from core.knowledge_base.models import Document, Category
from core.spaced_repetition.queue_manager import QueueManager

logger = logging.getLogger(__name__)

class QueueView(QWidget):
    """Widget for managing the document reading queue."""
    
    documentSelected = pyqtSignal(int)  # document_id
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.queue_manager = QueueManager(db_session)
        
        # Create UI
        self._create_ui()
        
        # Load initial data
        self._load_queue_data()
    
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
        
        self.prev_button = QPushButton("Previous Document")
        self.prev_button.clicked.connect(self._on_read_prev)
        self.prev_button.setToolTip("Open the previous document in the queue")
        nav_buttons_layout.addWidget(self.prev_button)
        
        self.read_next_button = QPushButton("Next Document")
        self.read_next_button.clicked.connect(self._on_read_next)
        self.read_next_button.setToolTip("Open the next document in the queue")
        nav_buttons_layout.addWidget(self.read_next_button)
        
        buttons_layout.addLayout(nav_buttons_layout)
        
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
            
            # Get queue statistics
            stats = self.queue_manager.get_queue_stats()
            
            # Update stats display
            self.total_label.setText(str(stats['total_documents']))
            self.due_today_label.setText(str(stats['due_today']))
            self.due_week_label.setText(str(stats['due_this_week']))
            self.overdue_label.setText(str(stats['overdue']))
            self.new_label.setText(str(stats['new_documents']))
            
            # Load documents by due date
            doc_by_date = self.queue_manager.get_documents_by_due_date(
                days=days_ahead,
                category_id=category_id,
                include_new=include_new
            )
            
            # Populate queue table
            self._populate_queue_table(doc_by_date)
            
            # Populate calendar view
            self._populate_calendar_view(doc_by_date)
            
        except Exception as e:
            logger.exception(f"Error loading queue data: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error loading queue data: {str(e)}"
            )
    
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
        """Handle read next document button click."""
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
            
            # If found and not the last one, get the next document
            if current_row >= 0 and current_row < self.queue_table.rowCount() - 1:
                next_doc_id = self.queue_table.item(current_row + 1, 0).data(Qt.ItemDataRole.UserRole)
                self.documentSelected.emit(next_doc_id)
                return
        
        # If no current document or it's the last one, get the first document in the queue
        if self.queue_table.rowCount() > 0:
            first_doc_id = self.queue_table.item(0, 0).data(Qt.ItemDataRole.UserRole)
            self.documentSelected.emit(first_doc_id)
        else:
            QMessageBox.information(
                self, "No Documents", 
                "There are no documents in the queue matching your filters."
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
        if self.queue_manager.update_document_priority(doc_id, priority):
            self._load_queue_data()
        else:
            QMessageBox.warning(
                self, "Error", 
                f"Failed to update document priority."
            )
    
    def _on_rate_document(self, doc_id: int, rating: int):
        """Handle rating a document."""
        result = self.queue_manager.schedule_document(doc_id, rating)
        
        if result:
            # Show scheduling info
            QMessageBox.information(
                self, "Document Scheduled", 
                f"Document rated as {rating}/5.\n"
                f"Next review in {result['interval_days']} days."
            )
            
            # Reload queue data
            self._load_queue_data()
        else:
            QMessageBox.warning(
                self, "Error", 
                f"Failed to schedule document."
            )
