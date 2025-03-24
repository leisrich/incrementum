# ui/export_dialog.py

import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QListWidget, QListWidgetItem, 
    QCheckBox, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QGroupBox,
    QFormLayout, QLineEdit, QTextEdit, QComboBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, pyqtSlot

from core.knowledge_base.models import Extract, LearningItem
from core.knowledge_base.export_manager import ExportManager

logger = logging.getLogger(__name__)

class ExportDialog(QDialog):
    """Dialog for exporting knowledge items."""
    
    def __init__(self, db_session, extract_ids=None, item_ids=None, parent=None):
        super().__init__(parent)
        
        self.db_session = db_session
        self.export_manager = ExportManager(db_session)
        self.extract_ids = extract_ids or []
        self.item_ids = item_ids or []
        
        # Create UI
        self._create_ui()
        
        # Load items
        self._load_items()
    
    def _create_ui(self):
        """Create the UI layout."""
        self.setWindowTitle("Export Knowledge Items")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        main_layout = QVBoxLayout(self)
        
        # Content to export
        content_group = QGroupBox("Content to Export")
        content_layout = QVBoxLayout(content_group)
        
        # Export type selection
        type_layout = QHBoxLayout()
        
        self.export_type_group = QButtonGroup(self)
        
        self.extracts_radio = QRadioButton("Extracts")
        self.items_radio = QRadioButton("Learning Items")
        self.deck_radio = QRadioButton("Complete Deck")
        self.all_data_radio = QRadioButton("All Data")
        
        self.export_type_group.addButton(self.extracts_radio)
        self.export_type_group.addButton(self.items_radio)
        self.export_type_group.addButton(self.deck_radio)
        self.export_type_group.addButton(self.all_data_radio)
        
        # Default to selected type based on provided IDs
        if self.extract_ids:
            self.extracts_radio.setChecked(True)
        elif self.item_ids:
            self.items_radio.setChecked(True)
        else:
            self.all_data_radio.setChecked(True)
        
        type_layout.addWidget(self.extracts_radio)
        type_layout.addWidget(self.items_radio)
        type_layout.addWidget(self.deck_radio)
        type_layout.addWidget(self.all_data_radio)
        content_layout.addLayout(type_layout)
        
        # Item selection list
        self.items_list = QListWidget()
        self.items_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        content_layout.addWidget(self.items_list)
        
        # Include learning items option (for extracts)
        self.include_items_check = QCheckBox("Include related learning items")
        self.include_items_check.setChecked(True)
        content_layout.addWidget(self.include_items_check)
        
        main_layout.addWidget(content_group)
        
        # Export options
        options_group = QGroupBox("Export Options")
        options_layout = QFormLayout(options_group)
        
        # Format selection
        self.format_combo = QComboBox()
        self.format_combo.addItem("JSON", "json")
        self.format_combo.addItem("Markdown", "markdown")
        self.format_combo.addItem("Plain Text", "text")
        options_layout.addRow("Format:", self.format_combo)
        
        # Filename
        filename_layout = QHBoxLayout()
        self.filename_edit = QLineEdit()
        self.filename_edit.setText(f"incrementum_export_{datetime.now().strftime('%Y%m%d')}")
        
        self.browse_button = QPushButton("Browse...")
        filename_layout.addWidget(self.filename_edit)
        filename_layout.addWidget(self.browse_button)
        options_layout.addRow("Filename:", filename_layout)
        
        # Optional description
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("Optional description for this export")
        self.description_edit.setMaximumHeight(80)
        options_layout.addRow("Description:", self.description_edit)
        
        main_layout.addWidget(options_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.export_button = QPushButton("Export")
        self.cancel_button = QPushButton("Cancel")
        
        button_layout.addStretch()
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # Connect signals
        self.export_type_group.buttonClicked.connect(self._on_export_type_changed)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        self.browse_button.clicked.connect(self._on_browse)
        self.export_button.clicked.connect(self._on_export)
        self.cancel_button.clicked.connect(self.reject)
        
        # Initial UI update
        self._on_export_type_changed()
    
    def _load_items(self):
        """Load items based on selection type."""
        self.items_list.clear()
        
        if self.extracts_radio.isChecked():
            # Load extracts
            if self.extract_ids:
                extracts = self.db_session.query(Extract).filter(Extract.id.in_(self.extract_ids)).all()
                
                for extract in extracts:
                    # Create list item with shortened content
                    content = extract.content
                    if len(content) > 100:
                        content = content[:97] + "..."
                    
                    item = QListWidgetItem(content)
                    item.setData(Qt.ItemDataRole.UserRole, extract.id)
                    item.setSelected(True)  # Select by default
                    self.items_list.addItem(item)
            else:
                # No extracts specified, show message
                self.items_list.addItem("No extracts selected")
        
        elif self.items_radio.isChecked():
            # Load learning items
            if self.item_ids:
                items = self.db_session.query(LearningItem).filter(LearningItem.id.in_(self.item_ids)).all()
                
                for item in items:
                    # Create list item with question
                    question = item.question
                    if len(question) > 100:
                        question = question[:97] + "..."
                    
                    list_item = QListWidgetItem(question)
                    list_item.setData(Qt.ItemDataRole.UserRole, item.id)
                    list_item.setSelected(True)  # Select by default
                    self.items_list.addItem(list_item)
            else:
                # No items specified, try to load items from extracts
                if self.extract_ids:
                    items = self.db_session.query(LearningItem).filter(
                        LearningItem.extract_id.in_(self.extract_ids)
                    ).all()
                    
                    for item in items:
                        # Create list item with question
                        question = item.question
                        if len(question) > 100:
                            question = question[:97] + "..."
                        
                        list_item = QListWidgetItem(question)
                        list_item.setData(Qt.ItemDataRole.UserRole, item.id)
                        list_item.setSelected(True)  # Select by default
                        self.items_list.addItem(list_item)
                else:
                    # No items or extracts specified, show message
                    self.items_list.addItem("No learning items selected")
        
        elif self.deck_radio.isChecked():
            # For deck export, we use extracts as the base
            if self.extract_ids:
                extracts = self.db_session.query(Extract).filter(Extract.id.in_(self.extract_ids)).all()
                
                for extract in extracts:
                    # Create list item with shortened content
                    content = extract.content
                    if len(content) > 100:
                        content = content[:97] + "..."
                    
                    item = QListWidgetItem(content)
                    item.setData(Qt.ItemDataRole.UserRole, extract.id)
                    item.setSelected(True)  # Select by default
                    self.items_list.addItem(item)
            else:
                # No extracts specified, show message
                self.items_list.addItem("No extracts selected for deck export")
    
    def _load_extracts(self):
        """Load extracts for selection."""
        self.items_list.clear()
        
        # Get recent extracts
        extracts = self.db_session.query(Extract).order_by(Extract.created_date.desc()).limit(100).all()
        
        if extracts:
            for extract in extracts:
                # Create list item with shortened content
                content = extract.content
                if len(content) > 100:
                    content = content[:97] + "..."
                
                item = QListWidgetItem(content)
                item.setData(Qt.ItemDataRole.UserRole, extract.id)
                
                # Pre-select if it's in the initial extracts list
                if self.extract_ids and extract.id in self.extract_ids:
                    item.setSelected(True)
                
                self.items_list.addItem(item)
        else:
            # No extracts in database
            item = QListWidgetItem("No extracts found in database")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.items_list.addItem(item)
    
    def _load_learning_items(self):
        """Load learning items for selection."""
        self.items_list.clear()
        
        # Get recent learning items
        items = self.db_session.query(LearningItem).order_by(LearningItem.created_date.desc()).limit(100).all()
        
        if items:
            for item in items:
                # Create list item with question
                question = item.question
                if len(question) > 100:
                    question = question[:97] + "..."
                
                list_item = QListWidgetItem(question)
                list_item.setData(Qt.ItemDataRole.UserRole, item.id)
                
                # Pre-select if it's in the initial items list
                if self.item_ids and item.id in self.item_ids:
                    list_item.setSelected(True)
                
                self.items_list.addItem(list_item)
        else:
            # No learning items in database
            item = QListWidgetItem("No learning items found in database")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.items_list.addItem(item)
    
    @pyqtSlot()
    def _on_export_type_changed(self):
        """Handle export type change."""
        # Update UI based on selected export type
        if self.extracts_radio.isChecked():
            self.items_list.setEnabled(True)
            self.include_items_check.setEnabled(True)
            self.include_items_check.setVisible(True)
            self._load_extracts()
        
        elif self.items_radio.isChecked():
            self.items_list.setEnabled(True)
            self.include_items_check.setEnabled(False)
            self.include_items_check.setVisible(False)
            self._load_learning_items()
        
        elif self.deck_radio.isChecked():
            self.items_list.setEnabled(True)
            self.include_items_check.setEnabled(False)
            self.include_items_check.setVisible(False)
            self._load_extracts()
        
        elif self.all_data_radio.isChecked():
            self.items_list.setEnabled(False)
            self.include_items_check.setEnabled(False)
            self.include_items_check.setVisible(False)
            self.items_list.clear()
            item = QListWidgetItem("All data will be exported")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.items_list.addItem(item)
        
        # Update filename
        self._update_filename()
    
    @pyqtSlot()
    def _on_format_changed(self):
        """Handle format selection change."""
        # Adjust UI based on selected format
        format_type = self.format_combo.currentData()
        
        if format_type == "izd":
            # Package format forces deck export
            self.deck_radio.setChecked(True)
            self.format_combo.setEnabled(False)
        else:
            # JSON format allows any export type
            self.format_combo.setEnabled(True)
    
    @pyqtSlot()
    def _on_export(self):
        """Handle export button click."""
        # Get file path
        file_format = self.format_combo.currentData()
        extension = ".json" if file_format == "json" else ".md" if file_format == "markdown" else ".txt"
        
        filepath = self.filename_edit.text()
        if not filepath.endswith(extension):
            filepath += extension
        
        # Check if file exists
        if os.path.exists(filepath):
            reply = QMessageBox.question(
                self, "File Exists", 
                f"File '{filepath}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Perform export based on selected type
        success = False
        if self.all_data_radio.isChecked():
            # Export all data
            success = self.export_manager.export_all_data(filepath, file_format)
            
            if success:
                QMessageBox.information(
                    self, "Export Complete", 
                    f"All data has been exported to:\n{filepath}"
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self, "Export Failed", 
                    f"Failed to export all data. Check the logs for details."
                )
        
        elif self.extracts_radio.isChecked():
            # Get selected extracts
            selected_items = self.items_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(
                    self, "No Selection", 
                    "Please select at least one extract to export."
                )
                return
            
            # Get extract IDs
            extract_ids = [
                item.data(Qt.ItemDataRole.UserRole)
                for item in selected_items
            ]
            
            # Export extracts
            include_items = self.include_items_check.isChecked()
            success = self.export_manager.export_extracts(extract_ids, filepath, include_items)
            
            if success:
                QMessageBox.information(
                    self, "Export Complete", 
                    f"Exported {len(extract_ids)} extracts to:\n{filepath}"
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self, "Export Failed", 
                    f"Failed to export extracts. Check the logs for details."
                )
        
        elif self.items_radio.isChecked():
            # Get selected learning items
            selected_items = self.items_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(
                    self, "No Selection", 
                    "Please select at least one learning item to export."
                )
                return
            
            # Get learning item IDs
            item_ids = [
                item.data(Qt.ItemDataRole.UserRole)
                for item in selected_items
            ]
            
            # Export learning items
            success = self.export_manager.export_learning_items(item_ids, filepath)
            
            if success:
                QMessageBox.information(
                    self, "Export Complete", 
                    f"Exported {len(item_ids)} learning items to:\n{filepath}"
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self, "Export Failed", 
                    f"Failed to export learning items. Check the logs for details."
                )
        
        elif self.deck_radio.isChecked():
            # Get selected extracts
            selected_items = self.items_list.selectedItems()
            if not selected_items:
                QMessageBox.warning(
                    self, "No Selection", 
                    "Please select at least one extract to include in the deck."
                )
                return
            
            # Get extract IDs
            extract_ids = [
                item.data(Qt.ItemDataRole.UserRole)
                for item in selected_items
            ]
            
            # Export deck
            success = self.export_manager.export_deck(extract_ids, filepath)
            
            if success:
                QMessageBox.information(
                    self, "Export Complete", 
                    f"Exported deck with {len(extract_ids)} extracts to:\n{filepath}"
                )
                self.accept()
            else:
                QMessageBox.critical(
                    self, "Export Failed", 
                    f"Failed to export deck. Check the logs for details."
                )
    
    def _update_filename(self):
        """Update the suggested filename based on export type."""
        date_str = datetime.now().strftime('%Y%m%d')
        
        if self.extracts_radio.isChecked():
            filename = f"incrementum_extracts_{date_str}"
        elif self.items_radio.isChecked():
            filename = f"incrementum_learningitems_{date_str}"
        elif self.deck_radio.isChecked():
            filename = f"incrementum_deck_{date_str}"
        elif self.all_data_radio.isChecked():
            filename = f"incrementum_alldata_{date_str}"
        else:
            filename = f"incrementum_export_{date_str}"
        
        self.filename_edit.setText(filename)
    
    @pyqtSlot()
    def _on_browse(self):
        """Handle browse button click to select file save location."""
        # Get appropriate file extension based on selected format
        file_format = self.format_combo.currentData()
        if file_format == "json":
            file_filter = "JSON Files (*.json)"
            extension = ".json"
        elif file_format == "markdown":
            file_filter = "Markdown Files (*.md)"
            extension = ".md"
        else:  # text format
            file_filter = "Text Files (*.txt)"
            extension = ".txt"
        
        # Get the current filename
        current_filename = self.filename_edit.text()
        if not current_filename.endswith(extension):
            current_filename += extension
        
        # Open file save dialog
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export To", current_filename, file_filter
        )
        
        if filepath:
            # Update filename field
            self.filename_edit.setText(filepath)
