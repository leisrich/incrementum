# ui/arxiv_dialog.py

import logging
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSpinBox, QComboBox,
    QProgressBar, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize

from core.document_processor.arxiv_importer import ArxivImporter
from core.document_processor.processor import DocumentProcessor
from core.knowledge_base.models import Category

logger = logging.getLogger(__name__)

class ArxivDialog(QDialog):
    """Dialog for searching and importing papers from Arxiv."""
    
    paperImported = pyqtSignal(int)  # document_id
    
    def __init__(self, document_processor: DocumentProcessor, db_session, parent=None):
        super().__init__(parent)
        
        self.document_processor = document_processor
        self.db_session = db_session
        self.arxiv_importer = ArxivImporter(document_processor)
        self.search_results = []
        
        # Create UI
        self._create_ui()
    
    def _create_ui(self):
        """Create the UI layout."""
        self.setWindowTitle("Import from Arxiv")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        
        main_layout = QVBoxLayout(self)
        
        # Search controls
        search_group = QGroupBox("Search")
        search_layout = QVBoxLayout(search_group)
        
        # Search input
        search_input_layout = QHBoxLayout()
        
        search_label = QLabel("Search Query:")
        search_input_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search terms (e.g., 'machine learning', 'author:Hinton', etc.)")
        self.search_input.returnPressed.connect(self._on_search)
        search_input_layout.addWidget(self.search_input)
        
        search_layout.addLayout(search_input_layout)
        
        # Search options
        options_layout = QHBoxLayout()
        
        options_layout.addWidget(QLabel("Max Results:"))
        self.max_results = QSpinBox()
        self.max_results.setRange(1, 100)
        self.max_results.setValue(10)
        options_layout.addWidget(self.max_results)
        
        options_layout.addStretch()
        
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._on_search)
        options_layout.addWidget(self.search_button)
        
        search_layout.addLayout(options_layout)
        
        main_layout.addWidget(search_group)
        
        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Title", "Authors", "Published", "Summary"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.doubleClicked.connect(self._on_result_selected)
        
        main_layout.addWidget(self.results_table)
        
        # Import controls
        import_group = QGroupBox("Import")
        import_layout = QFormLayout(import_group)
        
        # Category selection
        self.category_combo = QComboBox()
        self.category_combo.addItem("None", None)
        
        # Load categories
        categories = self.db_session.query(Category).order_by(Category.name).all()
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
        
        import_layout.addRow("Category:", self.category_combo)
        
        main_layout.addWidget(import_group)
        
        # Status bar
        status_layout = QHBoxLayout()
        
        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)
        
        main_layout.addLayout(status_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.import_button = QPushButton("Import Selected")
        self.import_button.clicked.connect(self._on_import_selected)
        self.import_button.setEnabled(False)
        button_layout.addWidget(self.import_button)
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        button_layout.addWidget(self.close_button)
        
        main_layout.addLayout(button_layout)
    
    @pyqtSlot()
    def _on_search(self):
        """Handle search button click."""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(
                self, "Empty Query", 
                "Please enter a search query."
            )
            return
        
        # Update UI
        self.status_label.setText(f"Searching Arxiv for: {query}")
        self.search_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(20)
        
        # Perform search
        max_results = self.max_results.value()
        self.search_results = self.arxiv_importer.search_papers(query, max_results)
        
        # Update progress
        self.progress_bar.setValue(80)
        
        # Display results
        self._display_search_results()
        
        # Update UI
        self.search_button.setEnabled(True)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Found {len(self.search_results)} papers")
        self.progress_bar.setVisible(False)
    
    def _display_search_results(self):
        """Display search results in the table."""
        # Clear table
        self.results_table.setRowCount(0)
        
        # Add rows
        for i, paper in enumerate(self.search_results):
            self.results_table.insertRow(i)
            
            # Title
            title_item = QTableWidgetItem(paper['title'])
            self.results_table.setItem(i, 0, title_item)
            
            # Authors
            authors_item = QTableWidgetItem(paper['author'])
            self.results_table.setItem(i, 1, authors_item)
            
            # Published date
            published_item = QTableWidgetItem(paper['published'][:10])  # Just the date part
            self.results_table.setItem(i, 2, published_item)
            
            # Summary
            summary = paper['summary']
            if len(summary) > 300:
                summary = summary[:297] + "..."
            summary_item = QTableWidgetItem(summary)
            self.results_table.setItem(i, 3, summary_item)
        
        # Enable import button if we have results
        self.import_button.setEnabled(len(self.search_results) > 0)
    
    @pyqtSlot()
    def _on_import_selected(self):
        """Handle import button click."""
        selected_rows = self.results_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(
                self, "No Selection", 
                "Please select a paper to import."
            )
            return
        
        # Get selected paper
        row = selected_rows[0].row()
        paper = self.search_results[row]
        
        # Get category
        category_id = self.category_combo.currentData()
        
        # Update UI
        self.status_label.setText(f"Importing: {paper['title']}")
        self.import_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(10)
        
        # Import paper
        document_id = self.arxiv_importer.import_paper(paper, category_id)
        
        # Update progress
        self.progress_bar.setValue(90)
        
        if document_id:
            self.status_label.setText(f"Imported: {paper['title']}")
            
            # Emit signal
            self.paperImported.emit(document_id)
            
            # Success message
            QMessageBox.information(
                self, "Import Successful", 
                f"Successfully imported paper: {paper['title']}"
            )
            
            # Close dialog
            self.accept()
        else:
            self.status_label.setText(f"Import failed: {paper['title']}")
            self.import_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            
            QMessageBox.warning(
                self, "Import Failed", 
                f"Failed to import paper: {paper['title']}"
            )
    
    @pyqtSlot()
    def _on_result_selected(self):
        """Handle double-click on result."""
        self._on_import_selected()
