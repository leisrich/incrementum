import logging
import datetime
import os
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QComboBox, QApplication, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QIcon, QColor

from core.knowledge_base.models import Document, IncrementalReading
from core.spaced_repetition.incremental_reading import IncrementalReadingManager

logger = logging.getLogger(__name__)

class IncrementalReadingView(QWidget):
    """View for managing incremental reading queue."""
    
    open_document_signal = pyqtSignal(int)  # Document ID
    
    def __init__(self, db_session):
        super().__init__()
        self.db_session = db_session
        self.ir_manager = IncrementalReadingManager(db_session)
        
        self.initUI()
        self.load_reading_queue()
    
    def initUI(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.load_reading_queue)
        toolbar_layout.addWidget(self.refresh_btn)
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems([
            "Priority (High to Low)", 
            "Due Date (Earliest First)",
            "Recently Added",
            "Percent Complete"
        ])
        self.sort_combo.currentIndexChanged.connect(self.load_reading_queue)
        toolbar_layout.addWidget(QLabel("Sort by:"))
        toolbar_layout.addWidget(self.sort_combo)
        
        toolbar_layout.addStretch()
        
        self.export_btn = QPushButton("Export Queue")
        self.export_btn.clicked.connect(self._export_reading_queue)
        toolbar_layout.addWidget(self.export_btn)
        
        self.auto_schedule_btn = QPushButton("Auto Schedule")
        self.auto_schedule_btn.clicked.connect(self.auto_schedule_readings)
        toolbar_layout.addWidget(self.auto_schedule_btn)
        
        layout.addLayout(toolbar_layout)
        
        # Reading queue table
        self.queue_table = QTableWidget()
        self.queue_table.setColumnCount(7)
        self.queue_table.setHorizontalHeaderLabels([
            "Title", "Priority", "Added Date", "Last Read", 
            "Next Read", "Progress", "Actions"
        ])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.queue_table)
        
        # Stats at bottom
        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("Loading statistics...")
        stats_layout.addWidget(self.stats_label)
        layout.addLayout(stats_layout)
        
    def load_reading_queue(self):
        """Load the reading queue into the table."""
        try:
            # Get sort option
            sort_index = self.sort_combo.currentIndex()
            sort_options = [
                {"field": "reading_priority", "order": "desc"},
                {"field": "next_read_date", "order": "asc"},
                {"field": "created_date", "order": "desc"},
                {"field": "percent_complete", "order": "asc"}
            ]
            
            # Get reading items
            readings = self.ir_manager.get_reading_queue(
                sort_field=sort_options[sort_index]["field"],
                sort_order=sort_options[sort_index]["order"]
            )
            
            # Set table rows
            self.queue_table.setRowCount(len(readings))
            
            for row, (reading, document) in enumerate(readings):
                # Title
                title_item = QTableWidgetItem(document.title)
                title_item.setData(Qt.ItemDataRole.UserRole, reading.id)
                self.queue_table.setItem(row, 0, title_item)
                
                # Priority
                priority_item = QTableWidgetItem(f"{reading.reading_priority:.1f}")
                self.queue_table.setItem(row, 1, priority_item)
                
                # Added date
                added_date = reading.created_date.strftime("%Y-%m-%d") if reading.created_date else ""
                self.queue_table.setItem(row, 2, QTableWidgetItem(added_date))
                
                # Last read date
                last_read = reading.last_read_date.strftime("%Y-%m-%d") if reading.last_read_date else "Never"
                self.queue_table.setItem(row, 3, QTableWidgetItem(last_read))
                
                # Next read date
                next_read = reading.next_read_date.strftime("%Y-%m-%d") if reading.next_read_date else ""
                next_read_item = QTableWidgetItem(next_read)
                
                # Highlight due items
                if reading.next_read_date and reading.next_read_date <= datetime.datetime.now():
                    next_read_item.setBackground(QColor(255, 235, 156))  # Light yellow
                
                self.queue_table.setItem(row, 4, next_read_item)
                
                # Progress
                progress_item = QTableWidgetItem(f"{reading.percent_complete:.1f}%")
                self.queue_table.setItem(row, 5, progress_item)
                
                # Actions cell
                actions_widget = QWidget()
                actions_layout = QHBoxLayout(actions_widget)
                actions_layout.setContentsMargins(2, 2, 2, 2)
                
                # Open button
                open_btn = QPushButton("Read")
                open_btn.setProperty("reading_id", reading.id)
                open_btn.setProperty("document_id", reading.document_id)
                open_btn.clicked.connect(self._on_open_document)
                actions_layout.addWidget(open_btn)
                
                self.queue_table.setCellWidget(row, 6, actions_widget)
            
            # Update stats
            today = datetime.datetime.now().date()
            due_count = sum(1 for r, _ in readings if r.next_read_date and r.next_read_date.date() <= today)
            
            stats_text = (
                f"Total items: {len(readings)} | "
                f"Due today: {due_count} | "
                f"Average progress: {self.ir_manager.get_average_progress():.1f}%"
            )
            self.stats_label.setText(stats_text)
                
        except Exception as e:
            logger.exception(f"Error loading reading queue: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while loading the reading queue: {str(e)}"
            )
    
    def _on_open_document(self):
        """Open the selected document."""
        sender = self.sender()
        if not sender:
            return
            
        document_id = sender.property("document_id")
        reading_id = sender.property("reading_id")
        
        if document_id:
            # Emit signal to open document
            self.open_document_signal.emit(document_id)
            
            # Mark as viewed
            self.ir_manager.mark_reading_viewed(reading_id)
    
    def _show_context_menu(self, position):
        """Show context menu for queue items."""
        row = self.queue_table.rowAt(position.y())
        if row < 0:
            return
            
        reading_id = self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # Create context menu
        context_menu = QMenu(self)
        
        open_action = QAction("Open Document", self)
        open_action.triggered.connect(lambda: self._context_open_document(reading_id))
        context_menu.addAction(open_action)
        
        context_menu.addSeparator()
        
        priority_menu = QMenu("Change Priority", context_menu)
        for p in [10, 30, 50, 70, 90]:
            action = QAction(f"Set to {p}", self)
            action.triggered.connect(lambda checked, p=p: self._context_change_priority(reading_id, p))
            priority_menu.addAction(action)
        context_menu.addMenu(priority_menu)
        
        reschedule_action = QAction("Reschedule", self)
        reschedule_action.triggered.connect(lambda: self._context_reschedule(reading_id))
        context_menu.addAction(reschedule_action)
        
        context_menu.addSeparator()
        
        remove_action = QAction("Remove from Queue", self)
        remove_action.triggered.connect(lambda: self._context_remove(reading_id))
        context_menu.addAction(remove_action)
        
        # Show the menu
        context_menu.exec(self.queue_table.mapToGlobal(position))
    
    def _context_open_document(self, reading_id):
        """Open document from context menu."""
        reading = self.db_session.query(IncrementalReading).get(reading_id)
        if reading:
            self.open_document_signal.emit(reading.document_id)
            self.ir_manager.mark_reading_viewed(reading_id)
    
    def _context_change_priority(self, reading_id, priority):
        """Change priority from context menu."""
        try:
            self.ir_manager.update_reading_priority(reading_id, priority)
            self.load_reading_queue()
        except Exception as e:
            logger.exception(f"Error changing priority: {e}")
            QMessageBox.warning(self, "Error", f"Failed to change priority: {str(e)}")
    
    def _context_reschedule(self, reading_id):
        """Reschedule reading from context menu."""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCalendarWidget, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Reschedule Reading")
            layout = QVBoxLayout(dialog)
            
            # Calendar widget
            calendar = QCalendarWidget(dialog)
            min_date = datetime.datetime.now().date()
            calendar.setMinimumDate(min_date)
            layout.addWidget(calendar)
            
            # Buttons
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | 
                QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected_date = calendar.selectedDate().toPyDate()
                self.ir_manager.reschedule_reading(reading_id, selected_date)
                self.load_reading_queue()
                
        except Exception as e:
            logger.exception(f"Error rescheduling: {e}")
            QMessageBox.warning(self, "Error", f"Failed to reschedule: {str(e)}")
    
    def _context_remove(self, reading_id):
        """Remove reading from queue."""
        try:
            confirm = QMessageBox.question(
                self, "Confirm Removal",
                "Are you sure you want to remove this item from the reading queue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if confirm == QMessageBox.StandardButton.Yes:
                self.ir_manager.remove_from_queue(reading_id)
                self.load_reading_queue()
                
        except Exception as e:
            logger.exception(f"Error removing reading: {e}")
            QMessageBox.warning(self, "Error", f"Failed to remove reading: {str(e)}")
    
    def auto_schedule_readings(self):
        """Auto-schedule readings based on priority and available time."""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDialogButtonBox
            
            dialog = QDialog(self)
            dialog.setWindowTitle("Auto Schedule Readings")
            layout = QVBoxLayout(dialog)
            
            # Items per day input
            items_layout = QHBoxLayout()
            items_layout.addWidget(QLabel("Items per day:"))
            items_spin = QSpinBox()
            items_spin.setRange(1, 20)
            items_spin.setValue(3)
            items_layout.addWidget(items_spin)
            layout.addLayout(items_layout)
            
            # Days to schedule input
            days_layout = QHBoxLayout()
            days_layout.addWidget(QLabel("Days to schedule:"))
            days_spin = QSpinBox()
            days_spin.setRange(1, 90)
            days_spin.setValue(14)
            days_layout.addWidget(days_spin)
            layout.addLayout(days_layout)
            
            # Buttons
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | 
                QDialogButtonBox.StandardButton.Cancel
            )
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                items_per_day = items_spin.value()
                days = days_spin.value()
                
                scheduled = self.ir_manager.auto_schedule_readings(
                    items_per_day=items_per_day,
                    days=days
                )
                
                self.load_reading_queue()
                
                QMessageBox.information(
                    self, "Auto Schedule", 
                    f"Successfully scheduled {scheduled} reading sessions over {days} days."
                )
                
        except Exception as e:
            logger.exception(f"Error auto-scheduling: {e}")
            QMessageBox.warning(self, "Error", f"Failed to auto-schedule readings: {str(e)}")
    
    def _export_reading_queue(self):
        """Export reading queue as SuperMemo HTML."""
        try:
            from PyQt6.QtWidgets import QFileDialog
            from core.spaced_repetition.sm_html_exporter import SuperMemoHTMLExporter
            
            # Ask for output directory
            output_dir = QFileDialog.getExistingDirectory(
                self, "Select Output Directory", os.path.expanduser("~")
            )
            
            if not output_dir:
                return
                
            # Export HTML
            exporter = SuperMemoHTMLExporter(self.db_session)
            result = exporter.export_reading_queue(output_dir)
            
            if result:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"Reading queue exported to:\n{result}"
                )
            else:
                QMessageBox.warning(
                    self, "Export Failed", 
                    "Failed to export reading queue. Check if there are items in the queue."
                )
                
        except Exception as e:
            logger.exception(f"Error exporting reading queue: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            ) 