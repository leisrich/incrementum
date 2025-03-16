# ui/export_dialog.py

import os
import logging
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
        
        self.type_group = QButtonGroup(self)
        
        self.extracts_radio = QRadioButton("Extracts")
        self.extracts_radio.setChecked(True)
        self.type_group.addButton(self.extracts_radio)
        type_layout.addWidget(self.extracts_radio)
        
        self.items_radio = QRadioButton("Learning Items")
        self.type_group.addButton(self.items_radio)
        type_layout.addWidget(self.items_radio)
        
        self.deck_radio = QRadioButton("Complete Deck")
        self.type_group.addButton(self.deck_radio)
        type_layout.addWidget(self.deck_radio)
        
        # Connect signals
        self.extracts_radio.toggled.connect(self._on_export_type_changed)
        self.items_radio.toggled.connect(self._on_export_type_changed)
        self.deck_radio.toggled.connect(self._on_export_type_changed)
        
        content_layout.addLayout(type_layout)
        
        # Include learning items checkbox (for extracts)
        self.include_items_check = QCheckBox("Include linked learning items")
        self.include_items_check.setChecked(True)
        content_layout.addWidget(self.include_items_check)
        
        # Deck title (for deck export)
        deck_title_layout = QFormLayout()
        self.deck_title = QLineEdit()
        self.deck_title.setText(f"Incrementum Deck - {datetime.now().strftime('%Y-%m-%d')}")
        deck_title_layout.addRow("Deck Title:", self.deck_title)
        content_layout.addLayout(deck_title_layout)
        
        # Deck description (for deck export)
        deck_desc_layout = QFormLayout()
        self.deck_description = QTextEdit()
        self.deck_description.setMaximumHeight(100)
        self.deck_description.setText("Exported from Incrementum")
        deck_desc_layout.addRow("Description:", self.deck_description)
        content_layout.addLayout(deck_desc_layout)
        
        # Items list
        self.items_list = QListWidget()
        self.items_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        content_layout.addWidget(self.items_list)
        
        main_layout.addWidget(content_group)
        
        # Export options
        options_group = QGroupBox("Export Options")
        options_layout = QFormLayout(options_group)
        
        # Format selection
        self.format_combo = QComboBox()
        self.format_combo.addItem("JSON Format (.json)", "json")
        self.format_combo.addItem("Deck Package (.izd)", "izd")
        options_layout.addRow("Export Format:", self.format_combo)
        
        # Connect signals
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        
        main_layout.addWidget(options_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.export_button = QPushButton("Export...")
        self.export_button.clicked.connect(self._on_export)
        button_layout.addWidget(self.export_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # Initial UI state
        self._on_export_type_changed()
        self._on_format_changed()
    
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
    
    @pyqtSlot()
    def _on_export_type_changed(self):
        """Handle export type selection change."""
        # Update UI based on selection
        if self.extracts_radio.isChecked():
            self.include_items_check.setVisible(True)
            self.deck_title.setVisible(False)
            self.deck_description.setVisible(False)
            self.format_combo.setEnabled(True)
        elif self.items_radio.isChecked():
            self.include_items_check.setVisible(False)
            self.deck_title.setVisible(False)
            self.deck_description.setVisible(False)
            self.format_combo.setEnabled(True)
        elif self.deck_radio.isChecked():
            self.include_items_check.setVisible(False)
            self.deck_title.setVisible(True)
            self.deck_description.setVisible(True)
            # Force package format for deck
            self.format_combo.setCurrentIndex(1)  # Deck Package
            self.format_combo.setEnabled(False)
        
        # Reload items
        self._load_items()
    
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
        # Get selected IDs
        selected_ids = []
        for i in range(self.items_list.count()):
            item = self.items_list.item(i)
            if item.isSelected():
                item_id = item.data(Qt.ItemDataRole.UserRole)
                if item_id is not None:
                    selected_ids.append(item_id)
        
        if not selected_ids:
            QMessageBox.warning(
                self, "No Items Selected", 
                "Please select at least one item to export."
            )
            return
        
        # Get export format
        format_type = self.format_combo.currentData()
        
        # Get file extension
        if format_type == "json":
            file_ext = ".json"
            file_filter = "JSON Files (*.json)"
        else:  # izd
            file_ext = ".izd"
            file_filter = "Incrementum Deck Files (*.izd)"
        
        # Get save path
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export To", "", file_filter
        )
        
        if not filepath:
            return
        
        # Add extension if missing
        if not filepath.endswith(file_ext):
            filepath += file_ext
        
        # Perform export based on type
        success = False
        
        if self.extracts_radio.isChecked():
            # Export extracts
            include_items = self.include_items_check.isChecked()
            success = self.export_manager.export_extracts(selected_ids, filepath, include_items)
            
            if success:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"Successfully exported {len(selected_ids)} extracts to {filepath}"
                )
        
        elif self.items_radio.isChecked():
            # Export learning items
            success = self.export_manager.export_learning_items(selected_ids, filepath)
            
            if success:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"Successfully exported {len(selected_ids)} learning items to {filepath}"
                )
        
        elif self.deck_radio.isChecked():
            # Export deck
            success = self.export_manager.export_deck(selected_ids, filepath)
            
            if success:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"Successfully exported deck with {len(selected_ids)} extracts to {filepath}"
                )
        
        if success:
            self.accept()
        else:
            QMessageBox.warning(
                self, "Export Failed", 
                f"Failed to export to {filepath}"
            )
