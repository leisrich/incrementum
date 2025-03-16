# ui/extract_view.py

import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QComboBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QGroupBox, QFormLayout, QToolBar,
    QLineEdit, QMessageBox, QMenu, QListWidget,
    QListWidgetItem, QDialog, QCheckBox, QTabWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize, QModelIndex
from PyQt6.QtGui import QAction, QIcon, QTextCursor, QColor
from PyQt6.QtCore import QPoint

from core.knowledge_base.models import Extract, LearningItem, Tag
from core.content_extractor.nlp_extractor import NLPExtractor
from ui.learning_item_editor import LearningItemEditor

logger = logging.getLogger(__name__)

class TagDialog(QDialog):
    """Dialog for managing tags."""
    
    def __init__(self, db_session, extract, parent=None):
        super().__init__(parent)
        
        self.db_session = db_session
        self.extract = extract
        
        self.setWindowTitle("Manage Tags")
        self.setMinimumWidth(300)
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Current tags
        current_tags_group = QGroupBox("Current Tags")
        current_tags_layout = QVBoxLayout(current_tags_group)
        
        self.current_tags_list = QListWidget()
        self.current_tags_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        current_tags_layout.addWidget(self.current_tags_list)
        
        layout.addWidget(current_tags_group)
        
        # Add new tag
        new_tag_group = QGroupBox("Add New Tag")
        new_tag_layout = QHBoxLayout(new_tag_group)
        
        self.new_tag_input = QLineEdit()
        self.new_tag_input.setPlaceholderText("Enter new tag")
        new_tag_layout.addWidget(self.new_tag_input)
        
        self.add_tag_button = QPushButton("Add")
        self.add_tag_button.clicked.connect(self._on_add_tag)
        new_tag_layout.addWidget(self.add_tag_button)
        
        layout.addWidget(new_tag_group)
        
        # Suggestions
        if hasattr(parent, 'nlp_extractor'):
            suggested_tags = parent.nlp_extractor.suggest_tags_for_extract(extract.id, max_suggestions=5)
            
            if suggested_tags:
                suggestions_group = QGroupBox("Suggested Tags")
                suggestions_layout = QVBoxLayout(suggestions_group)
                
                self.suggested_tags_list = QListWidget()
                
                for tag in suggested_tags:
                    item = QListWidgetItem(tag)
                    self.suggested_tags_list.addItem(item)
                
                self.suggested_tags_list.itemDoubleClicked.connect(self._on_suggestion_clicked)
                suggestions_layout.addWidget(self.suggested_tags_list)
                
                layout.addWidget(suggestions_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self._on_remove_tags)
        button_layout.addWidget(self.remove_button)
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        # Load current tags
        self._load_current_tags()
    
    def _load_current_tags(self):
        """Load current tags into list."""
        self.current_tags_list.clear()
        
        for tag in self.extract.tags:
            item = QListWidgetItem(tag.name)
            item.setData(Qt.ItemDataRole.UserRole, tag.id)
            self.current_tags_list.addItem(item)
    
    @pyqtSlot()
    def _on_add_tag(self):
        """Add a new tag."""
        tag_name = self.new_tag_input.text().strip()
        if not tag_name:
            return
        
        # Check if tag already exists
        for i in range(self.current_tags_list.count()):
            if self.current_tags_list.item(i).text() == tag_name:
                return
        
        # Get or create tag
        tag = self.db_session.query(Tag).filter(Tag.name == tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            self.db_session.add(tag)
            self.db_session.flush()
        
        # Add tag to extract
        self.extract.tags.append(tag)
        self.db_session.commit()
        
        # Update list
        self._load_current_tags()
        
        # Clear input
        self.new_tag_input.clear()
    
    @pyqtSlot()
    def _on_remove_tags(self):
        """Remove selected tags."""
        selected_items = self.current_tags_list.selectedItems()
        if not selected_items:
            return
        
        for item in selected_items:
            tag_id = item.data(Qt.ItemDataRole.UserRole)
            
            # Get tag
            tag = self.db_session.query(Tag).get(tag_id)
            if tag:
                # Remove from extract
                self.extract.tags.remove(tag)
        
        # Save changes
        self.db_session.commit()
        
        # Update list
        self._load_current_tags()
    
    @pyqtSlot(QListWidgetItem)
    def _on_suggestion_clicked(self, item):
        """Add suggested tag when clicked."""
        tag_name = item.text()
        
        # Check if already in current tags
        for i in range(self.current_tags_list.count()):
            if self.current_tags_list.item(i).text() == tag_name:
                return
        
        # Add the tag
        self.new_tag_input.setText(tag_name)
        self._on_add_tag()


class ExtractView(QWidget):
    """Widget for viewing and editing extracts."""
    
    extractSaved = pyqtSignal(int)  # extract_id
    extractDeleted = pyqtSignal(int)  # extract_id
    
    def __init__(self, extract, db_session):
        super().__init__()
        
        self.extract = extract
        self.db_session = db_session
        self.nlp_extractor = NLPExtractor(db_session)
        
        # Set up UI
        self._create_ui()
        
        # Load extract data
        self._load_extract_data()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        
        # Save action
        self.save_action = QAction("Save", self)
        self.save_action.triggered.connect(self._on_save)
        toolbar.addAction(self.save_action)
        
        toolbar.addSeparator()
        
        # Tags action
        self.tags_action = QAction("Manage Tags", self)
        self.tags_action.triggered.connect(self._on_manage_tags)
        toolbar.addAction(self.tags_action)
        
        # Generate items action
        self.generate_action = QAction("Generate Learning Items", self)
        self.generate_action.triggered.connect(self._on_generate_items)
        toolbar.addAction(self.generate_action)
        
        toolbar.addSeparator()
        
        # Delete action
        self.delete_action = QAction("Delete Extract", self)
        self.delete_action.triggered.connect(self._on_delete)
        toolbar.addAction(self.delete_action)
        
        main_layout.addWidget(toolbar)
        
        # Content area
        content_tabs = QTabWidget()
        
        # Extract tab
        extract_tab = QWidget()
        extract_layout = QVBoxLayout(extract_tab)
        
        # Extract metadata
        metadata_form = QFormLayout()
        
        # Document
        self.document_label = QLabel()
        if self.extract.document:
            self.document_label.setText(self.extract.document.title)
        else:
            self.document_label.setText("No document")
        metadata_form.addRow("Document:", self.document_label)
        
        # Date
        self.date_label = QLabel()
        if self.extract.created_date:
            self.date_label.setText(self.extract.created_date.strftime("%Y-%m-%d %H:%M"))
        metadata_form.addRow("Created:", self.date_label)
        
        # Priority
        priority_layout = QHBoxLayout()
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 100)
        self.priority_spin.setValue(self.extract.priority or 50)
        priority_layout.addWidget(self.priority_spin)
        
        self.priority_apply = QPushButton("Apply")
        self.priority_apply.clicked.connect(self._on_priority_changed)
        priority_layout.addWidget(self.priority_apply)
        
        metadata_form.addRow("Priority:", priority_layout)
        
        # Tags
        self.tags_label = QLabel()
        self._update_tags_label()
        metadata_form.addRow("Tags:", self.tags_label)
        
        extract_layout.addLayout(metadata_form)
        
        # Extract content
        extract_layout.addWidget(QLabel("<b>Content:</b>"))
        
        self.content_edit = QTextEdit()
        extract_layout.addWidget(self.content_edit)
        
        content_tabs.addTab(extract_tab, "Extract")
        
        # Learning Items tab
        items_tab = QWidget()
        items_layout = QVBoxLayout(items_tab)
        
        # Learning items table
        self.items_table = QTableWidget()
        self.items_table.setColumnCount(4)
        self.items_table.setHorizontalHeaderLabels(["Type", "Question", "Answer", "Priority"])
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.items_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.items_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.items_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.items_table.customContextMenuRequested.connect(self._on_items_context_menu)
        self.items_table.doubleClicked.connect(self._on_item_double_clicked)
        
        items_layout.addWidget(self.items_table)
        
        # New item button
        self.new_item_button = QPushButton("Create New Learning Item")
        self.new_item_button.clicked.connect(self._on_new_item)
        items_layout.addWidget(self.new_item_button)
        
        content_tabs.addTab(items_tab, "Learning Items")
        
        main_layout.addWidget(content_tabs)
    
    def _load_extract_data(self):
        """Load extract data into UI."""
        # Set content
        self.content_edit.setText(self.extract.content)
        
        # Load learning items
        self._load_learning_items()
    
    def _load_learning_items(self):
        """Load learning items into table."""
        # Clear table
        self.items_table.setRowCount(0)
        
        # Get learning items
        items = self.db_session.query(LearningItem).filter(
            LearningItem.extract_id == self.extract.id
        ).all()
        
        # Add to table
        for i, item in enumerate(items):
            self.items_table.insertRow(i)
            
            # Type
            type_item = QTableWidgetItem(item.item_type)
            self.items_table.setItem(i, 0, type_item)
            
            # Question
            question = item.question
            if len(question) > 100:
                question = question[:97] + "..."
                
            question_item = QTableWidgetItem(question)
            question_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.items_table.setItem(i, 1, question_item)
            
            # Answer
            answer = item.answer
            if len(answer) > 100:
                answer = answer[:97] + "..."
                
            answer_item = QTableWidgetItem(answer)
            self.items_table.setItem(i, 2, answer_item)
            
            # Priority
            priority_item = QTableWidgetItem(str(item.priority))
            self.items_table.setItem(i, 3, priority_item)
        
        # Update tab title
        parent = self.parent()
        if isinstance(parent, QTabWidget):
            tab_index = parent.indexOf(self)
            if tab_index >= 0:
                parent.setTabText(tab_index, f"Extract ({len(items)} items)")
    
    def _update_tags_label(self):
        """Update the tags label with current tags."""
        if not self.extract.tags:
            self.tags_label.setText("No tags")
        else:
            tags_text = ", ".join(tag.name for tag in self.extract.tags)
            self.tags_label.setText(tags_text)
    
    @pyqtSlot()
    def _on_save(self):
        """Save changes to the extract."""
        # Update content
        new_content = self.content_edit.toPlainText()
        if new_content != self.extract.content:
            self.extract.content = new_content
            self.db_session.commit()
            
            # Emit signal
            self.extractSaved.emit(self.extract.id)
            
            QMessageBox.information(
                self, "Extract Saved", 
                "Extract content has been saved successfully."
            )
    
    @pyqtSlot()
    def _on_priority_changed(self):
        """Update extract priority."""
        new_priority = self.priority_spin.value()
        if new_priority != self.extract.priority:
            self.extract.priority = new_priority
            self.db_session.commit()
            
            # Emit signal
            self.extractSaved.emit(self.extract.id)
    
    @pyqtSlot()
    def _on_manage_tags(self):
        """Show tag management dialog."""
        dialog = TagDialog(self.db_session, self.extract, self)
        if dialog.exec():
            # Update tags label
            self._update_tags_label()
    
    @pyqtSlot()
    def _on_generate_items(self):
        """Generate learning items."""
        # Ask for type
        dialog = QDialog(self)
        dialog.setWindowTitle("Generate Learning Items")
        dialog.setMinimumWidth(300)
        
        layout = QVBoxLayout(dialog)
        
        # Type selection
        type_group = QGroupBox("Item Type")
        type_layout = QVBoxLayout(type_group)
        
        qa_radio = QRadioButton("Question-Answer")
        qa_radio.setChecked(True)
        type_layout.addWidget(qa_radio)
        
        cloze_radio = QRadioButton("Cloze Deletion")
        type_layout.addWidget(cloze_radio)
        
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Count selection
        count_form = QFormLayout()
        count_spin = QSpinBox()
        count_spin.setRange(1, 10)
        count_spin.setValue(3)
        count_form.addRow("Number of items:", count_spin)
        layout.addLayout(count_form)
        
        # Open items option
        open_check = QCheckBox("Open items in editor after generation")
        open_check.setChecked(True)
        layout.addWidget(open_check)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)
        
        generate_button = QPushButton("Generate")
        generate_button.clicked.connect(dialog.accept)
        button_layout.addWidget(generate_button)
        
        layout.addLayout(button_layout)
        
        # Show dialog
        if not dialog.exec():
            return
        
        try:
            # Generate items
            if qa_radio.isChecked():
                # Generate QA items
                items = self.nlp_extractor.generate_qa_pairs(self.extract.id, max_pairs=count_spin.value())
            else:
                # Generate cloze items
                items = self.nlp_extractor.generate_cloze_deletions(self.extract.id, max_items=count_spin.value())
            
            # Mark extract as processed
            self.extract.processed = True
            self.db_session.commit()
            
            # Reload items
            self._load_learning_items()
            
            # Show success message
            QMessageBox.information(
                self, "Items Generated", 
                f"Successfully generated {len(items)} learning items."
            )
            
            # Open first item if requested
            if open_check.isChecked() and items:
                self._open_learning_item(items[0].id)
            
        except Exception as e:
            logger.exception(f"Error generating learning items: {e}")
            QMessageBox.warning(
                self, "Generation Failed", 
                f"Failed to generate learning items: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_delete(self):
        """Delete the extract."""
        # Count learning items
        items_count = self.db_session.query(LearningItem).filter(
            LearningItem.extract_id == self.extract.id
        ).count()
        
        # Confirmation
        msg = "Are you sure you want to delete this extract?"
        
        if items_count > 0:
            msg += f"\n\nThis will also delete {items_count} learning items."
        
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Get ID before deletion
                extract_id = self.extract.id
                
                # Delete extract (cascades to learning items)
                self.db_session.delete(self.extract)
                self.db_session.commit()
                
                # Emit signal
                self.extractDeleted.emit(extract_id)
                
                # Show success message
                QMessageBox.information(
                    self, "Extract Deleted", 
                    "Extract has been deleted successfully."
                )
                
                # Close the tab
                parent = self.parent()
                if isinstance(parent, QTabWidget):
                    index = parent.indexOf(self)
                    if index >= 0:
                        parent.removeTab(index)
                
            except Exception as e:
                logger.exception(f"Error deleting extract: {e}")
                QMessageBox.warning(
                    self, "Deletion Failed", 
                    f"Failed to delete extract: {str(e)}"
                )
    
    @pyqtSlot(QModelIndex)
    def _on_item_double_clicked(self, index):
        """Handle double-click on learning item."""
        # Get item ID
        item_id = self.items_table.item(index.row(), 1).data(Qt.ItemDataRole.UserRole)
        
        # Open learning item
        self._open_learning_item(item_id)
    
    def _open_learning_item(self, item_id):
        """Open learning item in editor."""
        # Create editor in a new tab
        editor = LearningItemEditor(self.db_session, item_id)
        
        # Connect signals
        editor.itemSaved.connect(self._on_item_saved)
        editor.itemDeleted.connect(self._on_item_deleted)
        
        # Find parent tab widget
        parent = self.parent()
        while parent and not isinstance(parent, QTabWidget):
            parent = parent.parent()
        
        if parent:
            # Add to parent's parent (tab widget)
            tab_index = parent.addTab(editor, f"Item {item_id}")
            parent.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_new_item(self):
        """Create a new learning item."""
        # Create editor in a new tab
        editor = LearningItemEditor(self.db_session, extract_id=self.extract.id)
        
        # Connect signals
        editor.itemSaved.connect(self._on_item_saved)
        
        # Find parent tab widget
        parent = self.parent()
        while parent and not isinstance(parent, QTabWidget):
            parent = parent.parent()
        
        if parent:
            # Add to parent's parent (tab widget)
            tab_index = parent.addTab(editor, "New Learning Item")
            parent.setCurrentIndex(tab_index)
    
    @pyqtSlot(int)
    def _on_item_saved(self, item_id):
        """Handle learning item save."""
        # Reload learning items
        self._load_learning_items()
    
    @pyqtSlot(int)
    def _on_item_deleted(self, item_id):
        """Handle learning item deletion."""
        # Reload learning items
        self._load_learning_items()
    
    @pyqtSlot(QPoint)
    def _on_items_context_menu(self, pos):
        """Show context menu for learning items table."""
        index = self.items_table.indexAt(pos)
        if not index.isValid():
            return
        
        # Get item ID
        row = index.row()
        item_id = self.items_table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        
        # Create menu
        menu = QMenu(self)
        
        edit_action = menu.addAction("Edit Item")
        edit_action.triggered.connect(lambda: self._open_learning_item(item_id))
        
        menu.addSeparator()
        
        delete_action = menu.addAction("Delete Item")
        delete_action.triggered.connect(lambda: self._on_delete_item(item_id))
        
        # Show menu
        menu.exec(self.items_table.viewport().mapToGlobal(pos))
    
    @pyqtSlot(int)
    def _on_delete_item(self, item_id):
        """Delete a learning item."""
        # Confirmation
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            "Are you sure you want to delete this learning item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Delete item
                item = self.db_session.query(LearningItem).get(item_id)
                if item:
                    self.db_session.delete(item)
                    self.db_session.commit()
                
                # Reload learning items
                self._load_learning_items()
                
            except Exception as e:
                logger.exception(f"Error deleting learning item: {e}")
                QMessageBox.warning(
                    self, "Deletion Failed", 
                    f"Failed to delete learning item: {str(e)}"
                )
