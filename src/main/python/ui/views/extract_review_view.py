"""
Extract Review View - For reviewing extracts in a group/category
"""

import logging
from datetime import datetime
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QSplitter, QComboBox, QTextEdit, QMessageBox,
    QFrame, QScrollArea, QToolBar, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QAction, QIcon

from sqlalchemy import select, update

from core.knowledge_base.models import Extract, Document, Category, LearningItem
from ..extract_view import ExtractView

logger = logging.getLogger(__name__)

class ExtractReviewView(QWidget):
    """View for reviewing multiple extracts, such as from a category."""
    
    extractUpdated = pyqtSignal(int)  # Extract ID that was updated
    extractDeleted = pyqtSignal(int)  # Extract ID that was deleted
    
    def __init__(self, db_session, parent=None):
        super().__init__(parent)
        
        self.db_session = db_session
        self.extracts = []
        self.current_index = 0
        self.title = "Extract Review"
        
        self._create_ui()
    
    def _create_ui(self):
        """Create the user interface."""
        main_layout = QVBoxLayout(self)
        
        # Toolbar for navigation and actions
        self._create_toolbar()
        main_layout.addWidget(self.toolbar)
        
        # Main splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter, 1)
        
        # Extract list (left side)
        self.extract_list_widget = QWidget()
        extract_list_layout = QVBoxLayout(self.extract_list_widget)
        extract_list_layout.setContentsMargins(0, 0, 0, 0)
        
        # Extract list header
        self.list_header = QLabel("Extracts")
        self.list_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        extract_list_layout.addWidget(self.list_header)
        
        # Extract list scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.extract_list_container = QWidget()
        self.extract_list_layout = QVBoxLayout(self.extract_list_container)
        self.extract_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.extract_list_layout.setSpacing(1)
        
        self.scroll_area.setWidget(self.extract_list_container)
        extract_list_layout.addWidget(self.scroll_area)
        
        # Extract view (right side)
        self.extract_view_container = QWidget()
        extract_view_layout = QVBoxLayout(self.extract_view_container)
        extract_view_layout.setContentsMargins(0, 0, 0, 0)
        
        # Extract view header
        self.view_header = QLabel("Extract Content")
        self.view_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        extract_view_layout.addWidget(self.view_header)
        
        # Current extract view will be added here when an extract is selected
        self.extract_view = None
        
        # Add placeholder
        self.placeholder = QLabel("Select an extract to view")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        extract_view_layout.addWidget(self.placeholder)
        
        # Add widgets to splitter
        self.main_splitter.addWidget(self.extract_list_widget)
        self.main_splitter.addWidget(self.extract_view_container)
        
        # Set splitter sizes
        self.main_splitter.setSizes([300, 700])
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self._on_prev_extract)
        nav_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self._on_next_extract)
        nav_layout.addWidget(self.next_button)
        
        main_layout.addLayout(nav_layout)
        
        # Update button states
        self._update_button_states()
    
    def _create_toolbar(self):
        """Create the toolbar."""
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(24, 24))
        
        # Add actions
        self.filter_action = QAction("Filter", self)
        self.filter_action.setToolTip("Filter extracts")
        self.filter_action.triggered.connect(self._on_filter)
        self.toolbar.addAction(self.filter_action)
        
        self.toolbar.addSeparator()
        
        self.sort_action = QAction("Sort", self)
        self.sort_action.setToolTip("Sort extracts")
        self.sort_action.triggered.connect(self._on_sort)
        self.toolbar.addAction(self.sort_action)
        
        self.toolbar.addSeparator()
        
        self.new_item_action = QAction("Create Learning Item", self)
        self.new_item_action.setToolTip("Create a new learning item from current extract")
        self.new_item_action.triggered.connect(self._on_create_learning_item)
        self.toolbar.addAction(self.new_item_action)
        
        self.edit_action = QAction("Edit Extract", self)
        self.edit_action.setToolTip("Edit the current extract")
        self.edit_action.triggered.connect(self._on_edit_extract)
        self.toolbar.addAction(self.edit_action)
        
        self.delete_action = QAction("Delete Extract", self)
        self.delete_action.setToolTip("Delete the current extract")
        self.delete_action.triggered.connect(self._on_delete_extract)
        self.toolbar.addAction(self.delete_action)
        
        # Add spacer
        spacer = QWidget()
        spacer.setSizePolicy(QWidget().sizePolicy().Policy.Expanding, QWidget().sizePolicy().Policy.Expanding)
        self.toolbar.addWidget(spacer)
        
        # Add label for count
        self.count_label = QLabel("0 extracts")
        self.toolbar.addWidget(self.count_label)
    
    def load_extracts(self, extracts: List[Extract], title: str = "Extract Review"):
        """Load extracts into the view.
        
        Args:
            extracts: List of Extract objects to load
            title: Title to display for this review session
        """
        self.extracts = extracts
        self.current_index = 0
        self.title = title
        
        # Update UI
        self.list_header.setText(f"{title} ({len(extracts)} extracts)")
        self.count_label.setText(f"{len(extracts)} extracts")
        
        # Clear previous extract items
        for i in reversed(range(self.extract_list_layout.count())):
            widget = self.extract_list_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        
        # Add extract items to list
        for i, extract in enumerate(self.extracts):
            item = self._create_extract_item(extract, i)
            self.extract_list_layout.addWidget(item)
        
        # Show first extract if available
        if self.extracts:
            self._show_extract(0)
        
        # Update button states
        self._update_button_states()
    
    def _create_extract_item(self, extract: Extract, index: int) -> QWidget:
        """Create a widget for an extract in the list.
        
        Args:
            extract: The Extract object
            index: The index in the extract list
            
        Returns:
            A widget representing the extract
        """
        item = QFrame()
        item.setFrameShape(QFrame.Shape.StyledPanel)
        item.setFrameShadow(QFrame.Shadow.Raised)
        item.setLineWidth(1)
        
        # Make clickable
        item.mousePressEvent = lambda event, idx=index: self._on_extract_clicked(idx)
        
        layout = QVBoxLayout(item)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Extract content preview (truncated)
        preview = extract.content
        if len(preview) > 100:
            preview = preview[:97] + "..."
        
        content_label = QLabel(preview)
        content_label.setWordWrap(True)
        layout.addWidget(content_label)
        
        # Document title if available
        if extract.document:
            doc_label = QLabel(f"From: {extract.document.title}")
            doc_label.setStyleSheet("color: gray; font-size: 9pt;")
            layout.addWidget(doc_label)
        
        # Date added
        date_label = QLabel(f"Added: {extract.created_date.strftime('%Y-%m-%d')}")
        date_label.setStyleSheet("color: gray; font-size: 9pt;")
        layout.addWidget(date_label)
        
        # Store the extract ID
        item.setProperty("extract_id", extract.id)
        item.setProperty("index", index)
        
        return item
    
    def _show_extract(self, index: int):
        """Show the extract at the given index.
        
        Args:
            index: Index of the extract to show
        """
        if index < 0 or index >= len(self.extracts):
            return
        
        self.current_index = index
        extract = self.extracts[index]
        
        # Clear the current extract view
        if self.extract_view:
            # Remove from layout
            for i in reversed(range(self.extract_view_container.layout().count())):
                widget = self.extract_view_container.layout().itemAt(i).widget()
                if widget != self.view_header:  # Keep the header
                    widget.deleteLater()
        
        # Hide placeholder
        self.placeholder.setVisible(False)
        
        # Create new extract view
        self.extract_view = ExtractView(extract, self.db_session)
        self.extract_view_container.layout().addWidget(self.extract_view)
        
        # Update header
        if extract.document:
            self.view_header.setText(f"Extract from: {extract.document.title}")
        else:
            self.view_header.setText(f"Extract {extract.id}")
        
        # Highlight the selected item in the list
        for i in range(self.extract_list_layout.count()):
            widget = self.extract_list_layout.itemAt(i).widget()
            if widget:
                widget_index = widget.property("index")
                if widget_index == index:
                    widget.setStyleSheet("background-color: #e6f2ff;")
                else:
                    widget.setStyleSheet("")
        
        # Update extract's last reviewed time
        try:
            extract.last_reviewed = datetime.utcnow()
            self.db_session.commit()
        except Exception as e:
            logger.error(f"Error updating extract last_reviewed time: {e}")
        
        # Update button states
        self._update_button_states()
    
    def _update_button_states(self):
        """Update the navigation button states."""
        if not self.extracts:
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.new_item_action.setEnabled(False)
            self.edit_action.setEnabled(False)
            self.delete_action.setEnabled(False)
            return
        
        self.prev_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.extracts) - 1)
        self.new_item_action.setEnabled(True)
        self.edit_action.setEnabled(True)
        self.delete_action.setEnabled(True)
    
    @pyqtSlot(int)
    def _on_extract_clicked(self, index: int):
        """Handle click on an extract item.
        
        Args:
            index: Index of the clicked extract
        """
        self._show_extract(index)
    
    @pyqtSlot()
    def _on_prev_extract(self):
        """Show the previous extract."""
        if self.current_index > 0:
            self._show_extract(self.current_index - 1)
    
    @pyqtSlot()
    def _on_next_extract(self):
        """Show the next extract."""
        if self.current_index < len(self.extracts) - 1:
            self._show_extract(self.current_index + 1)
    
    @pyqtSlot()
    def _on_filter(self):
        """Show filter options."""
        if not hasattr(self, 'filter_menu'):
            self.filter_menu = QMenu(self)
            
            # Add filter options
            self.filter_all_action = QAction("All Extracts", self)
            self.filter_all_action.triggered.connect(lambda: self._apply_filter("all"))
            self.filter_menu.addAction(self.filter_all_action)
            
            self.filter_unreviewed_action = QAction("Unreviewed", self)
            self.filter_unreviewed_action.triggered.connect(lambda: self._apply_filter("unreviewed"))
            self.filter_menu.addAction(self.filter_unreviewed_action)
            
            self.filter_no_items_action = QAction("No Learning Items", self)
            self.filter_no_items_action.triggered.connect(lambda: self._apply_filter("no_items"))
            self.filter_menu.addAction(self.filter_no_items_action)
            
            self.filter_menu.addSeparator()
            
            # Filter by priority
            self.filter_high_priority_action = QAction("High Priority", self)
            self.filter_high_priority_action.triggered.connect(lambda: self._apply_filter("high_priority"))
            self.filter_menu.addAction(self.filter_high_priority_action)
            
            self.filter_medium_priority_action = QAction("Medium Priority", self)
            self.filter_medium_priority_action.triggered.connect(lambda: self._apply_filter("medium_priority"))
            self.filter_menu.addAction(self.filter_medium_priority_action)
            
            self.filter_low_priority_action = QAction("Low Priority", self)
            self.filter_low_priority_action.triggered.connect(lambda: self._apply_filter("low_priority"))
            self.filter_menu.addAction(self.filter_low_priority_action)
        
        # Show the menu
        self.filter_menu.exec(self.mapToGlobal(self.toolbar.mapToParent(self.filter_action.icon().pixmap(16, 16).rect().topLeft())))
    
    def _apply_filter(self, filter_type: str):
        """Apply a filter to the extracts.
        
        Args:
            filter_type: Type of filter to apply
        """
        if not hasattr(self, 'all_extracts'):
            # Store all extracts for filtering
            self.all_extracts = self.extracts.copy()
        
        # Get the original title
        original_title = self.title
        if " - " in original_title:
            original_title = original_title.split(" - ")[0]
        
        filtered_extracts = []
        
        if filter_type == "all":
            filtered_extracts = self.all_extracts.copy()
            filter_name = "All"
        elif filter_type == "unreviewed":
            filtered_extracts = [e for e in self.all_extracts if not e.last_reviewed]
            filter_name = "Unreviewed"
        elif filter_type == "no_items":
            # Get extract IDs that have learning items
            item_extract_ids = set(item.extract_id for item in 
                                   self.db_session.execute(select(LearningItem.extract_id)).scalars().all())
            
            filtered_extracts = [e for e in self.all_extracts if e.id not in item_extract_ids]
            filter_name = "No Learning Items"
        elif filter_type == "high_priority":
            filtered_extracts = [e for e in self.all_extracts if e.priority >= 70]
            filter_name = "High Priority"
        elif filter_type == "medium_priority":
            filtered_extracts = [e for e in self.all_extracts if 30 <= e.priority < 70]
            filter_name = "Medium Priority"
        elif filter_type == "low_priority":
            filtered_extracts = [e for e in self.all_extracts if e.priority < 30]
            filter_name = "Low Priority"
        
        # Update the view with filtered extracts
        new_title = f"{original_title} - {filter_name}"
        self.load_extracts(filtered_extracts, new_title)
    
    @pyqtSlot()
    def _on_sort(self):
        """Show sort options."""
        if not hasattr(self, 'sort_menu'):
            self.sort_menu = QMenu(self)
            
            # Add sort options
            self.sort_date_asc_action = QAction("Date (Oldest First)", self)
            self.sort_date_asc_action.triggered.connect(lambda: self._apply_sort("date_asc"))
            self.sort_menu.addAction(self.sort_date_asc_action)
            
            self.sort_date_desc_action = QAction("Date (Newest First)", self)
            self.sort_date_desc_action.triggered.connect(lambda: self._apply_sort("date_desc"))
            self.sort_menu.addAction(self.sort_date_desc_action)
            
            self.sort_menu.addSeparator()
            
            self.sort_priority_asc_action = QAction("Priority (Lowest First)", self)
            self.sort_priority_asc_action.triggered.connect(lambda: self._apply_sort("priority_asc"))
            self.sort_menu.addAction(self.sort_priority_asc_action)
            
            self.sort_priority_desc_action = QAction("Priority (Highest First)", self)
            self.sort_priority_desc_action.triggered.connect(lambda: self._apply_sort("priority_desc"))
            self.sort_menu.addAction(self.sort_priority_desc_action)
            
            self.sort_menu.addSeparator()
            
            self.sort_review_asc_action = QAction("Last Reviewed (Oldest First)", self)
            self.sort_review_asc_action.triggered.connect(lambda: self._apply_sort("review_asc"))
            self.sort_menu.addAction(self.sort_review_asc_action)
            
            self.sort_review_desc_action = QAction("Last Reviewed (Newest First)", self)
            self.sort_review_desc_action.triggered.connect(lambda: self._apply_sort("review_desc"))
            self.sort_menu.addAction(self.sort_review_desc_action)
        
        # Show the menu
        self.sort_menu.exec(self.mapToGlobal(self.toolbar.mapToParent(self.sort_action.icon().pixmap(16, 16).rect().topLeft())))
    
    def _apply_sort(self, sort_type: str):
        """Apply a sort to the extracts.
        
        Args:
            sort_type: Type of sort to apply
        """
        if sort_type == "date_asc":
            self.extracts.sort(key=lambda e: e.created_date or datetime.min)
        elif sort_type == "date_desc":
            self.extracts.sort(key=lambda e: e.created_date or datetime.min, reverse=True)
        elif sort_type == "priority_asc":
            self.extracts.sort(key=lambda e: e.priority or 0)
        elif sort_type == "priority_desc":
            self.extracts.sort(key=lambda e: e.priority or 0, reverse=True)
        elif sort_type == "review_asc":
            self.extracts.sort(key=lambda e: e.last_reviewed or datetime.min)
        elif sort_type == "review_desc":
            self.extracts.sort(key=lambda e: e.last_reviewed or datetime.min, reverse=True)
        
        # Reload the extracts
        self.load_extracts(self.extracts, self.title)
    
    @pyqtSlot()
    def _on_create_learning_item(self):
        """Create a new learning item from the current extract."""
        if not self.extracts or self.current_index >= len(self.extracts):
            return
        
        extract = self.extracts[self.current_index]
        
        # Open learning item editor
        from ..learning_item_editor import LearningItemEditor
        editor = LearningItemEditor(self.db_session, extract_id=extract.id)
        
        # Get parent window
        parent = self.parent()
        if hasattr(parent, 'add_tab'):
            # If the parent has an add_tab method, use it
            parent.add_tab(editor, f"New Learning Item")
        else:
            # Otherwise just show the editor as a dialog
            editor.show()
    
    @pyqtSlot()
    def _on_edit_extract(self):
        """Edit the current extract."""
        if not self.extracts or self.current_index >= len(self.extracts):
            return
        
        extract = self.extracts[self.current_index]
        
        # Open extract editor
        from ..extract_editor import ExtractEditor
        editor = ExtractEditor(extract, self.db_session)
        
        if editor.exec() == editor.DialogCode.Accepted:
            # Update the extract in the list
            self.extractUpdated.emit(extract.id)
            
            # Refresh the current view
            self._show_extract(self.current_index)
    
    @pyqtSlot()
    def _on_delete_extract(self):
        """Delete the current extract."""
        if not self.extracts or self.current_index >= len(self.extracts):
            return
        
        extract = self.extracts[self.current_index]
        
        # Confirm deletion
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            f"Are you sure you want to delete this extract?\n\nThis will also delete any learning items created from it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Get the extract ID
            extract_id = extract.id
            
            try:
                # Delete the extract
                self.db_session.delete(extract)
                self.db_session.commit()
                
                # Remove from the list
                self.extracts.pop(self.current_index)
                
                # Emit signal
                self.extractDeleted.emit(extract_id)
                
                # Update the view
                self.load_extracts(self.extracts, self.title)
                
                # Show the next extract, or the previous if at the end
                if self.extracts:
                    if self.current_index >= len(self.extracts):
                        self._show_extract(len(self.extracts) - 1)
                    else:
                        self._show_extract(self.current_index)
                
            except Exception as e:
                logger.exception(f"Error deleting extract: {e}")
                QMessageBox.warning(
                    self, "Error", 
                    f"Failed to delete extract: {str(e)}"
                ) 