"""
Extract Editor - Dialog for editing extracts
"""

import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, 
    QPushButton, QTextEdit, QComboBox, QSpinBox, QDialogButtonBox,
    QCheckBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot

from sqlalchemy import select

from core.knowledge_base.models import Extract, Category

logger = logging.getLogger(__name__)

class ExtractEditor(QDialog):
    """Dialog for editing an extract."""
    
    def __init__(self, extract, db_session, parent=None):
        super().__init__(parent)
        
        self.extract = extract
        self.db_session = db_session
        
        self.setWindowTitle("Edit Extract")
        self.setMinimumSize(800, 600)
        
        self._create_ui()
        self._load_data()
    
    def _create_ui(self):
        """Create the user interface."""
        main_layout = QVBoxLayout(self)
        
        # Form for extract metadata
        form_layout = QFormLayout()
        
        # Document information (read-only)
        if self.extract.document:
            self.document_label = QLabel(f"From document: {self.extract.document.title}")
        else:
            self.document_label = QLabel("No associated document")
        form_layout.addRow("Document:", self.document_label)
        
        # Created date (read-only)
        date_str = self.extract.created_date.strftime("%Y-%m-%d %H:%M") if self.extract.created_date else "Unknown"
        self.created_date_label = QLabel(date_str)
        form_layout.addRow("Created:", self.created_date_label)
        
        # Priority
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(0, 100)
        self.priority_spin.setValue(self.extract.priority or 50)
        self.priority_spin.setToolTip("Higher priority extracts will be reviewed more frequently")
        form_layout.addRow("Priority:", self.priority_spin)
        
        # Category
        self.category_combo = QComboBox()
        form_layout.addRow("Category:", self.category_combo)
        
        # Processed flag
        self.processed_check = QCheckBox("Mark as processed")
        self.processed_check.setChecked(self.extract.processed or False)
        self.processed_check.setToolTip("Indicates this extract has been processed into learning items")
        form_layout.addRow("", self.processed_check)
        
        main_layout.addLayout(form_layout)
        
        # Extract content
        content_label = QLabel("Extract Content:")
        main_layout.addWidget(content_label)
        
        self.content_edit = QTextEdit()
        self.content_edit.setPlaceholderText("Extract content...")
        self.content_edit.setAcceptRichText(False)
        main_layout.addWidget(self.content_edit, 1)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_save)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)
    
    def _load_data(self):
        """Load data into the UI."""
        # Load categories
        self._load_categories()
        
        # Set content
        self.content_edit.setPlainText(self.extract.content or "")
    
    def _load_categories(self):
        """Load categories into the combo box."""
        try:
            # Clear existing items
            self.category_combo.clear()
            
            # Add "None" option
            self.category_combo.addItem("(None)", None)
            
            # Query all categories
            categories = self.db_session.execute(
                select(Category).order_by(Category.name)
            ).scalars().all()
            
            # Add to combo box
            for category in categories:
                self.category_combo.addItem(category.name, category.id)
            
            # Set current category
            current_index = 0
            if self.extract.category_id:
                for i in range(self.category_combo.count()):
                    if self.category_combo.itemData(i) == self.extract.category_id:
                        current_index = i
                        break
            
            self.category_combo.setCurrentIndex(current_index)
            
        except Exception as e:
            logger.exception(f"Error loading categories: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error loading categories: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_save(self):
        """Save changes to the extract."""
        try:
            # Update extract properties
            self.extract.content = self.content_edit.toPlainText()
            self.extract.priority = self.priority_spin.value()
            self.extract.category_id = self.category_combo.currentData()
            self.extract.processed = self.processed_check.isChecked()
            self.extract.modified_date = datetime.utcnow()
            
            # Save to database
            self.db_session.commit()
            
            # Accept the dialog
            self.accept()
            
        except Exception as e:
            logger.exception(f"Error saving extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error saving extract: {str(e)}"
            ) 