# ui/import_dialog.py

import os
import logging
from typing import List, Dict, Any, Optional, Set

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QGroupBox,
    QFormLayout, QComboBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, pyqtSlot

from core.knowledge_base.models import Document, Extract
from core.knowledge_base.export_manager import ExportManager

logger = logging.getLogger(__name__)

class ImportDialog(QDialog):
    """Dialog for importing knowledge items."""
    
    importCompleted = pyqtSignal(int, int, int)  # extracts, items, tags
    
    def __init__(self, db_session, parent=None):
        super().__init__(parent)
        
        self.db_session = db_session
        self.export_manager = ExportManager(db_session)
        
        # Create UI
        self._create_ui()
    
    def _create_ui(self):
        """Create the UI layout."""
        self.setWindowTitle("Import Knowledge Items")
        self.setMinimumWidth(500)
        
        main_layout = QVBoxLayout(self)
        
        # Import type selection
        type_group = QGroupBox("Import Type")
        type_layout = QVBoxLayout(type_group)
        
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
        
        main_layout.addWidget(type_group)
        
        # Import options
        options_group = QGroupBox("Import Options")
        options_layout = QFormLayout(options_group)
        
        # Source document selection (for extracts)
        self.document_combo = QComboBox()
        self.document_combo.addItem("None - Standalone Extracts", None)
        
        # Populate documents
        documents = self.db_session.query(Document).order_by(Document.title).all()
        for doc in documents:
            self.document_combo.addItem(doc.title, doc.id)
        
        options_layout.addRow("Target Document:", self.document_combo)
        
        # Target extract selection (for learning items)
        self.extract_combo = QComboBox()
        self.extract_combo.setEnabled(False)  # Initially disabled
        
        options_layout.addRow("Target Extract:", self.extract_combo)
        
        main_layout.addWidget(options_group)
        
        # File selection
        file_group = QGroupBox("File")
        file_layout = QHBoxLayout(file_group)
        
        self.file_path = QLabel("No file selected")
        file_layout.addWidget(self.file_path)
        
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._on_browse)
        file_layout.addWidget(self.browse_button)
        
        main_layout.addWidget(file_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self._on_import)
        self.import_button.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.import_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # Connect signals
        self.extracts_radio.toggled.connect(self._update_ui)
        self.items_radio.toggled.connect(self._update_ui)
        self.deck_radio.toggled.connect(self._update_ui)
        self.items_radio.toggled.connect(self._populate_extracts)
        
        # Initial UI update
        self._update_ui()
    
    def _update_ui(self):
        """Update UI based on import type."""
        # Document combo is only relevant for extracts import
        document_enabled = self.extracts_radio.isChecked()
        self.document_combo.setEnabled(document_enabled)
        
        # Extract combo is only relevant for learning items import
        extract_enabled = self.items_radio.isChecked()
        self.extract_combo.setEnabled(extract_enabled)
    
    def _populate_extracts(self):
        """Populate the extract combo box."""
        self.extract_combo.clear()
        
        if not self.items_radio.isChecked():
            return
        
        # Query extracts
        extracts = self.db_session.query(Extract).order_by(Extract.created_date.desc()).limit(50).all()
        
        for extract in extracts:
            # Create display text from extract content
            content = extract.content
            if len(content) > 50:
                content = content[:47] + "..."
            
            self.extract_combo.addItem(content, extract.id)
    
    @pyqtSlot()
    def _on_browse(self):
        """Handle browse button click."""
        # Determine file filter based on import type
        if self.deck_radio.isChecked():
            file_filter = "Incrementum Deck Files (*.izd)"
        else:
            file_filter = "JSON Files (*.json);;Incrementum Deck Files (*.izd)"
        
        # Get file path
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select File to Import", "", file_filter
        )
        
        if filepath:
            self.file_path.setText(filepath)
            self.import_button.setEnabled(True)
            
            # If it's a deck file, force deck import
            if filepath.lower().endswith('.izd'):
                self.deck_radio.setChecked(True)
    
    @pyqtSlot()
    def _on_import(self):
        """Handle import button click."""
        filepath = self.file_path.text()
        if filepath == "No file selected" or not os.path.exists(filepath):
            QMessageBox.warning(
                self, "Invalid File", 
                "Please select a valid file to import."
            )
            return
        
        # Perform import based on type
        if self.extracts_radio.isChecked():
            # Import extracts
            target_document_id = self.document_combo.currentData()
            extracts_count, items_count = self.export_manager.import_extracts(filepath, target_document_id)
            
            if extracts_count > 0:
                QMessageBox.information(
                    self, "Import Successful", 
                    f"Successfully imported {extracts_count} extracts and {items_count} learning items."
                )
                self.importCompleted.emit(extracts_count, items_count, 0)
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Import Failed", 
                    "Failed to import extracts from the file."
                )
        
        elif self.items_radio.isChecked():
            # Import learning items
            target_extract_id = self.extract_combo.currentData()
            if not target_extract_id:
                QMessageBox.warning(
                    self, "No Target Extract", 
                    "Please select a target extract for the learning items."
                )
                return
            
            items_count = self.export_manager.import_learning_items(filepath, target_extract_id)
            
            if items_count > 0:
                QMessageBox.information(
                    self, "Import Successful", 
                    f"Successfully imported {items_count} learning items."
                )
                self.importCompleted.emit(0, items_count, 0)
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Import Failed", 
                    "Failed to import learning items from the file."
                )
        
        elif self.deck_radio.isChecked():
            # Import deck
            extracts_count, items_count, tags_count = self.export_manager.import_deck(filepath)
            
            if extracts_count > 0 or items_count > 0:
                QMessageBox.information(
                    self, "Import Successful", 
                    f"Successfully imported deck with {extracts_count} extracts, "
                    f"{items_count} learning items, and {tags_count} tags."
                )
                self.importCompleted.emit(extracts_count, items_count, tags_count)
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Import Failed", 
                    "Failed to import deck from the file."
                )
