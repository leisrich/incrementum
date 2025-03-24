# ui/detailed_queue_view.py

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QComboBox, QFormLayout, QSpinBox, QSplitter,
    QMessageBox, QMenu, QCheckBox, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QApplication, QFrame, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QSize
from PyQt6.QtGui import QIcon, QColor, QBrush, QKeySequence, QShortcut

from core.knowledge_base.models import Document, Category, Extract, IncrementalReading
from core.spaced_repetition import FSRSAlgorithm
from core.utils.settings_manager import SettingsManager
from core.utils.shortcuts import ShortcutManager
from core.utils.category_helper import get_all_categories, populate_category_combo
from core.utils.theme_manager import ThemeManager

logger = logging.getLogger(__name__)

class DetailedQueueView(QWidget):
    """
    A detailed view of documents in the reading queue with 
    comprehensive information and statistics.
    """
    
    documentSelected = pyqtSignal(int)  # document_id
    
    def __init__(self, db_session, settings_manager=None):
        super().__init__()
        
        self.db_session = db_session
        self.settings_manager = settings_manager or SettingsManager()
        self.theme_manager = ThemeManager(self.settings_manager)
        
        # Initialize FSRS algorithm
        fsrs_params = self._get_fsrs_params()
        self.fsrs = FSRSAlgorithm(db_session, params=fsrs_params)
        
        # Create UI
        self._create_ui()
        
        # Load data
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
    
    def _create_ui(self):
        """Create the user interface."""
        main_layout = QVBoxLayout(self)
        
        # Create header with stats
        self.header_frame = QFrame()
        self.header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QHBoxLayout(self.header_frame)
        
        # Queue stats
        self.stats_label = QLabel("Loading queue statistics...")
        header_layout.addWidget(self.stats_label)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        
        # Category filter
        filter_layout.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.setMinimumWidth(150)
        
        # Add "All Categories" option
        self.category_combo.addItem("All Categories", None)
        
        # Populate with categories from database
        populate_category_combo(self.category_combo, self.db_session)
        self.category_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.category_combo)
        
        # Content type filter
        filter_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.setMinimumWidth(100)
        self.type_combo.addItem("All Types", "")
        self.type_combo.addItem("PDF", "pdf")
        self.type_combo.addItem("EPUB", "epub")
        self.type_combo.addItem("HTML", "html")
        self.type_combo.addItem("Text", "txt")
        self.type_combo.addItem("YouTube", "youtube")
        self.type_combo.addItem("Audio", "audio")
        self.type_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.type_combo)
        
        # Show only due items
        self.due_only_checkbox = QCheckBox("Due Only")
        self.due_only_checkbox.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.due_only_checkbox)
        
        header_layout.addLayout(filter_layout)
        main_layout.addWidget(self.header_frame)
        
        # Create queue table
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(8)
        self.queue_table.setHorizontalHeaderLabels([
            "Title", "Type", "Category", "Added", "Last Read", 
            "Next Read", "Priority", "Read Count"
        ])
        
        # Set column widths
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Title
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Type
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Category
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Added
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Last Read
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Next Read
        self.queue_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Priority
        self.queue_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Read Count
        
        # Connect double-click to open document
        self.queue_table.cellDoubleClicked.connect(self._on_document_double_clicked)
        
        # Enable context menu
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self._on_context_menu)
        
        # Add to layout
        main_layout.addWidget(self.queue_table)
        
        # Add button row
        button_layout = QHBoxLayout()
        
        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_icon = QIcon.fromTheme("view-refresh")
        if not refresh_icon.isNull():
            refresh_btn.setIcon(refresh_icon)
        else:
            refresh_btn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        refresh_btn.clicked.connect(self._load_queue_data)
        button_layout.addWidget(refresh_btn)
        
        # Rating buttons
        rate_layout = QHBoxLayout()
        rate_layout.addWidget(QLabel("Rate Selected:"))
        
        for i in range(1, 6):
            rate_btn = QPushButton(str(i))
            rate_btn.setFixedWidth(40)
            rate_btn.clicked.connect(lambda checked, rating=i: self._rate_selected_document(rating))
            rate_layout.addWidget(rate_btn)
        
        button_layout.addLayout(rate_layout)
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
        # Apply theme colors
        self._apply_theme()
    
    def _apply_theme(self):
        """Apply theme colors to the view."""
        # Use a simpler theme approach with QApplication's palette
        app_palette = QApplication.palette()
        
        # Apply a simple styling for the header frame
        header_style = """
            QFrame {
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
        """
        if hasattr(self, 'header_frame'):
            self.header_frame.setStyleSheet(header_style)
        
        # Use system colors for the table
        self.queue_table.setAlternatingRowColors(True)
        
        # Only set tab widget style if it exists
        if hasattr(self, 'tab_widget'):
            self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
            self.tab_widget.setDocumentMode(True)
    
    def _load_queue_data(self):
        """Load queue data from the database."""
        try:
            # Get filter values
            category_id = None
            if self.category_combo.currentData():
                category_id = self.category_combo.currentData()
                
            content_type = self.type_combo.currentData()
            due_only = self.due_only_checkbox.isChecked()
            
            # Query documents
            query = self.db_session.query(Document)
            
            # Apply filters
            if category_id:
                query = query.filter(Document.category_id == category_id)
                
            if content_type:
                if content_type == "audio":
                    query = query.filter(Document.content_type.in_(["mp3", "wav", "ogg", "flac", "m4a", "aac"]))
                else:
                    query = query.filter(Document.content_type == content_type)
            
            if due_only:
                now = datetime.now()
                query = query.filter(
                    (Document.next_reading_date.is_(None)) | 
                    (Document.next_reading_date <= now)
                )
            
            # Sort by priority (highest first) and next reading date (earliest first)
            documents = query.order_by(
                Document.priority.desc(),
                Document.next_reading_date.asc().nullsfirst()
            ).all()
            
            # Clear table
            self.queue_table.setRowCount(0)
            
            # Get category lookup
            categories = {c.id: c.name for c in self.db_session.query(Category).all()}
            
            # Fill table
            for i, doc in enumerate(documents):
                self.queue_table.insertRow(i)
                
                # Title
                title_item = QTableWidgetItem(doc.title)
                title_item.setData(Qt.ItemDataRole.UserRole, doc.id)
                self.queue_table.setItem(i, 0, title_item)
                
                # Content Type
                if doc.content_type in ["mp3", "wav", "ogg", "flac", "m4a", "aac"]:
                    type_text = f"Audio ({doc.content_type})"
                else:
                    type_text = doc.content_type.upper()
                self.queue_table.setItem(i, 1, QTableWidgetItem(type_text))
                
                # Category
                category_name = categories.get(doc.category_id, "None")
                self.queue_table.setItem(i, 2, QTableWidgetItem(category_name))
                
                # Imported Date
                if doc.imported_date:
                    date_str = doc.imported_date.strftime("%Y-%m-%d")
                    self.queue_table.setItem(i, 3, QTableWidgetItem(date_str))
                else:
                    self.queue_table.setItem(i, 3, QTableWidgetItem(""))
                
                # Last Reading Date
                if doc.last_reading_date:
                    date_str = doc.last_reading_date.strftime("%Y-%m-%d")
                    self.queue_table.setItem(i, 4, QTableWidgetItem(date_str))
                else:
                    self.queue_table.setItem(i, 4, QTableWidgetItem("Never"))
                
                # Next Reading Date
                next_date_item = QTableWidgetItem()
                if doc.next_reading_date:
                    date_str = doc.next_reading_date.strftime("%Y-%m-%d")
                    next_date_item.setText(date_str)
                    
                    # Highlight due items
                    if doc.next_reading_date <= datetime.now():
                        # Use a direct color for due items - red
                        next_date_item.setForeground(QBrush(QColor("#cc0000")))
                else:
                    next_date_item.setText("Due Now")
                    # Use a direct color for new items - green
                    next_date_item.setForeground(QBrush(QColor("#006600")))
                
                self.queue_table.setItem(i, 5, next_date_item)
                
                # Priority
                priority_item = QTableWidgetItem(str(doc.priority))
                self.queue_table.setItem(i, 6, priority_item)
                
                # Reading Count
                count_item = QTableWidgetItem(str(doc.reading_count))
                self.queue_table.setItem(i, 7, count_item)
            
            # Update statistics
            self._update_stats(documents)
            
        except Exception as e:
            logger.exception(f"Error loading queue data: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load queue data: {str(e)}")
    
    def _update_stats(self, documents: List[Document]):
        """Update queue statistics display."""
        total_count = len(documents)
        due_count = sum(1 for doc in documents if doc.next_reading_date is None or doc.next_reading_date <= datetime.now())
        new_count = sum(1 for doc in documents if doc.reading_count == 0)
        
        # Calculate average priority
        if documents:
            avg_priority = sum(doc.priority for doc in documents) / len(documents)
        else:
            avg_priority = 0
        
        # Update stats label
        stats_text = (
            f"<b>Queue Statistics:</b> "
            f"{total_count} documents total | "
            f"{due_count} due now | "
            f"{new_count} new | "
            f"Avg. Priority: {avg_priority:.1f}"
        )
        self.stats_label.setText(stats_text)
    
    def _on_filter_changed(self):
        """Handle filter changes by reloading data."""
        self._load_queue_data()
    
    def _on_document_double_clicked(self, row, column):
        """Handle double click on a document to open it."""
        item = self.queue_table.item(row, 0)  # Title column has the document ID
        document_id = item.data(Qt.ItemDataRole.UserRole)
        
        self.documentSelected.emit(document_id)
    
    def _on_context_menu(self, pos):
        """Show context menu for queue items."""
        # Get the item at the current position
        item = self.queue_table.itemAt(pos)
        if not item:
            return
            
        # Get the row of the item
        row = item.row()
        
        # Get document ID from the title column
        doc_id_item = self.queue_table.item(row, 0)
        if not doc_id_item:
            return
            
        document_id = doc_id_item.data(Qt.ItemDataRole.UserRole)
        
        # Create context menu
        menu = QMenu(self)
        
        # Add actions
        open_action = menu.addAction("Open Document")
        open_action.triggered.connect(lambda: self.documentSelected.emit(document_id))
        
        menu.addSeparator()
        
        # Rating submenu
        rating_menu = menu.addMenu("Rate Document")
        for i in range(1, 6):
            rate_action = rating_menu.addAction(f"Rate {i}")
            rate_action.triggered.connect(lambda checked, r=i, d=document_id: self._rate_document(d, r))
        
        menu.addSeparator()
        
        # Priority submenu
        priority_menu = menu.addMenu("Set Priority")
        for p in [10, 25, 50, 75, 90]:
            priority_action = priority_menu.addAction(f"Priority {p}")
            priority_action.triggered.connect(lambda checked, p=p, d=document_id: self._set_document_priority(d, p))
        
        # Show the menu
        menu.exec(self.queue_table.mapToGlobal(pos))
    
    def _rate_selected_document(self, rating: int):
        """Rate the currently selected document."""
        # Get selected row
        selected_rows = self.queue_table.selectedItems()
        if not selected_rows:
            return
            
        # Get document ID from the first selected row's title column
        row = selected_rows[0].row()
        doc_id_item = self.queue_table.item(row, 0)
        if not doc_id_item:
            return
            
        document_id = doc_id_item.data(Qt.ItemDataRole.UserRole)
        
        # Rate the document
        self._rate_document(document_id, rating)
    
    def _rate_document(self, document_id: int, rating: int):
        """Rate a document and update its scheduling."""
        try:
            # Get the document
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document not found: {document_id}")
                return
            
            # Calculate next reading date based on FSRS
            fsrs_card = self.fsrs.create_card_from_document(document)
            fsrs_rating = self.fsrs.convert_rating_to_fsrs(rating)
            fsrs_result = self.fsrs.process_response(fsrs_card, fsrs_rating)
            
            # Update document
            document.last_reading_date = datetime.now()
            document.next_reading_date = fsrs_result.next_date
            document.reading_count += 1
            document.stability = fsrs_result.stability
            document.difficulty = fsrs_result.difficulty
            
            # Save to database
            self.db_session.commit()
            
            # Update queue display
            self._load_queue_data()
            
            # Provide feedback
            days_until_next = (fsrs_result.next_date - datetime.now()).days
            QMessageBox.information(self, "Document Rated", 
                f"Document rated {rating}/5.\n"
                f"Next review scheduled in {days_until_next} days "
                f"on {fsrs_result.next_date.strftime('%Y-%m-%d')}."
            )
            
        except Exception as e:
            logger.exception(f"Error rating document: {e}")
            QMessageBox.warning(self, "Error", f"Failed to rate document: {str(e)}")
    
    def _set_document_priority(self, document_id: int, priority: int):
        """Set priority for a document."""
        try:
            # Get the document
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document not found: {document_id}")
                return
            
            # Update priority
            document.priority = priority
            self.db_session.commit()
            
            # Update queue display
            self._load_queue_data()
            
        except Exception as e:
            logger.exception(f"Error setting document priority: {e}")
            QMessageBox.warning(self, "Error", f"Failed to set document priority: {str(e)}") 