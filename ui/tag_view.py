# ui/tag_view.py

import logging
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QComboBox, QGroupBox, QMessageBox, QInputDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QSplitter, QMenu, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize, QPoint, QModelIndex
from PyQt6.QtGui import QIcon, QAction

from sqlalchemy import func
from core.knowledge_base.models import Document, Extract, Tag
from core.knowledge_base.tag_manager import TagManager

logger = logging.getLogger(__name__)

class TagView(QWidget):
    """Widget for managing tags."""
    
    itemSelected = pyqtSignal(str, int)  # type, id
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.tag_manager = TagManager(db_session)
        
        self.selected_tag_id = None
        
        # Create UI
        self._create_ui()
        
        # Load tags
        self._load_tags()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header
        header_label = QLabel("<h2>Tag Management</h2>")
        main_layout.addWidget(header_label)
        
        # Create the main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Tags panel
        tags_panel = QWidget()
        tags_layout = QVBoxLayout(tags_panel)
        
        # Tag list
        tags_group = QGroupBox("Tags")
        tags_inner_layout = QVBoxLayout(tags_group)
        
        # Tag filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.tag_filter = QLineEdit()
        self.tag_filter.setPlaceholderText("Type to filter tags...")
        self.tag_filter.textChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.tag_filter)
        tags_inner_layout.addLayout(filter_layout)
        
        # Tag list
        self.tag_list = QListWidget()
        self.tag_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.tag_list.itemSelectionChanged.connect(self._on_tag_selected)
        self.tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tag_list.customContextMenuRequested.connect(self._on_tag_context_menu)
        tags_inner_layout.addWidget(self.tag_list)
        
        # Tag operations
        tag_ops_layout = QHBoxLayout()
        
        self.add_tag_button = QPushButton("Add Tag")
        self.add_tag_button.clicked.connect(self._on_add_tag)
        tag_ops_layout.addWidget(self.add_tag_button)
        
        self.rename_tag_button = QPushButton("Rename")
        self.rename_tag_button.clicked.connect(self._on_rename_tag)
        self.rename_tag_button.setEnabled(False)  # Initially disabled
        tag_ops_layout.addWidget(self.rename_tag_button)
        
        self.delete_tag_button = QPushButton("Delete")
        self.delete_tag_button.clicked.connect(self._on_delete_tag)
        self.delete_tag_button.setEnabled(False)  # Initially disabled
        tag_ops_layout.addWidget(self.delete_tag_button)
        
        tags_inner_layout.addLayout(tag_ops_layout)
        
        # Tag merge/split operations
        tag_adv_ops_layout = QHBoxLayout()
        
        self.merge_tags_button = QPushButton("Merge Tags")
        self.merge_tags_button.clicked.connect(self._on_merge_tags)
        tag_adv_ops_layout.addWidget(self.merge_tags_button)
        
        self.export_tags_button = QPushButton("Export Tags")
        self.export_tags_button.clicked.connect(self._on_export_tags)
        tag_adv_ops_layout.addWidget(self.export_tags_button)
        
        tags_inner_layout.addLayout(tag_adv_ops_layout)
        
        tags_layout.addWidget(tags_group)
        
        # Tag statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout(stats_group)
        
        self.tag_stats_label = QLabel("No tag selected")
        stats_layout.addWidget(self.tag_stats_label)
        
        tags_layout.addWidget(stats_group)
        
        # Content panel
        content_panel = QWidget()
        content_layout = QVBoxLayout(content_panel)
        
        # Tag content tabs
        content_tabs = QTabWidget()
        
        # Documents tab
        self.documents_tab = QWidget()
        documents_layout = QVBoxLayout(self.documents_tab)
        
        self.documents_table = QTableWidget()
        self.documents_table.setColumnCount(3)
        self.documents_table.setHorizontalHeaderLabels(["Title", "Type", "Imported"])
        self.documents_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.documents_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.documents_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.documents_table.customContextMenuRequested.connect(self._on_document_context_menu)
        self.documents_table.doubleClicked.connect(self._on_document_selected)
        
        documents_layout.addWidget(self.documents_table)
        
        content_tabs.addTab(self.documents_tab, "Documents")
        
        # Extracts tab
        self.extracts_tab = QWidget()
        extracts_layout = QVBoxLayout(self.extracts_tab)
        
        self.extracts_table = QTableWidget()
        self.extracts_table.setColumnCount(3)
        self.extracts_table.setHorizontalHeaderLabels(["Content", "Document", "Created"])
        self.extracts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.extracts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.extracts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.extracts_table.customContextMenuRequested.connect(self._on_extract_context_menu)
        self.extracts_table.doubleClicked.connect(self._on_extract_selected)
        
        extracts_layout.addWidget(self.extracts_table)
        
        content_tabs.addTab(self.extracts_tab, "Extracts")
        
        content_layout.addWidget(content_tabs)
        
        # Add control buttons
        control_layout = QHBoxLayout()
        
        self.remove_tag_button = QPushButton("Remove Tag from Selected")
        self.remove_tag_button.clicked.connect(self._on_remove_tag_from_selected)
        self.remove_tag_button.setEnabled(False)  # Initially disabled
        control_layout.addWidget(self.remove_tag_button)
        
        content_layout.addLayout(control_layout)
        
        # Add widgets to splitter
        splitter.addWidget(tags_panel)
        splitter.addWidget(content_panel)
        splitter.setStretchFactor(0, 1)  # Tags panel
        splitter.setStretchFactor(1, 2)  # Content panel
        
        main_layout.addWidget(splitter)
    
    def _load_tags(self):
        """Load all tags into the list."""
        self.tag_list.clear()
        
        # Get all tags
        tags = self.tag_manager.get_all_tags()
        
        for tag in tags:
            item = QListWidgetItem(tag.name)
            item.setData(Qt.ItemDataRole.UserRole, tag.id)
            self.tag_list.addItem(item)
    
    def _update_tag_statistics(self, tag_id):
        """Update tag statistics display."""
        tag = self.db_session.query(Tag).get(tag_id)
        if not tag:
            self.tag_stats_label.setText("No tag selected")
            return
        
        # Count documents with this tag
        doc_count = self.db_session.query(func.count(Document.id)).filter(
            Document.tags.any(Tag.id == tag_id)
        ).scalar() or 0
        
        # Count extracts with this tag
        extract_count = self.db_session.query(func.count(Extract.id)).filter(
            Extract.tags.any(Tag.id == tag_id)
        ).scalar() or 0
        
        # Update label
        stats_text = f"<b>Tag: {tag.name}</b><br>"
        stats_text += f"Documents: {doc_count}<br>"
        stats_text += f"Extracts: {extract_count}<br>"
        stats_text += f"Total tagged items: {doc_count + extract_count}"
        
        self.tag_stats_label.setText(stats_text)
    
    def _load_tag_documents(self, tag_id):
        """Load documents with the selected tag."""
        # Clear table
        self.documents_table.setRowCount(0)
        
        # Get documents with this tag
        documents = self.db_session.query(Document).filter(
            Document.tags.any(Tag.id == tag_id)
        ).all()
        
        # Update tab title
        self.documents_tab.parentWidget().setTabText(0, f"Documents ({len(documents)})")
        
        # Add rows
        for i, doc in enumerate(documents):
            self.documents_table.insertRow(i)
            
            # Title
            title_item = QTableWidgetItem(doc.title)
            title_item.setData(Qt.ItemDataRole.UserRole, doc.id)
            self.documents_table.setItem(i, 0, title_item)
            
            # Type
            type_item = QTableWidgetItem(doc.content_type)
            self.documents_table.setItem(i, 1, type_item)
            
            # Imported date
            date_str = doc.imported_date.strftime("%Y-%m-%d") if doc.imported_date else ""
            date_item = QTableWidgetItem(date_str)
            self.documents_table.setItem(i, 2, date_item)
    
    def _load_tag_extracts(self, tag_id):
        """Load extracts with the selected tag."""
        # Clear table
        self.extracts_table.setRowCount(0)
        
        # Get extracts with this tag
        extracts = self.db_session.query(Extract).filter(
            Extract.tags.any(Tag.id == tag_id)
        ).all()
        
        # Update tab title
        self.extracts_tab.parentWidget().setTabText(1, f"Extracts ({len(extracts)})")
        
        # Add rows
        for i, extract in enumerate(extracts):
            self.extracts_table.insertRow(i)
            
            # Content
            content = extract.content
            if len(content) > 100:
                content = content[:97] + "..."
                
            content_item = QTableWidgetItem(content)
            content_item.setData(Qt.ItemDataRole.UserRole, extract.id)
            self.extracts_table.setItem(i, 0, content_item)
            
            # Document
            doc_title = extract.document.title if extract.document else "No document"
            doc_item = QTableWidgetItem(doc_title)
            self.extracts_table.setItem(i, 1, doc_item)
            
            # Created date
            date_str = extract.created_date.strftime("%Y-%m-%d") if extract.created_date else ""
            date_item = QTableWidgetItem(date_str)
            self.extracts_table.setItem(i, 2, date_item)
    
    @pyqtSlot(str)
    def _on_filter_changed(self, text):
        """Filter tags based on input text."""
        filter_text = text.lower()
        
        for i in range(self.tag_list.count()):
            item = self.tag_list.item(i)
            tag_name = item.text().lower()
            
            item.setHidden(filter_text not in tag_name)
    
    @pyqtSlot()
    def _on_tag_selected(self):
        """Handle tag selection change."""
        selected_items = self.tag_list.selectedItems()
        if not selected_items:
            # No selection
            self.selected_tag_id = None
            self.tag_stats_label.setText("No tag selected")
            self.documents_table.setRowCount(0)
            self.extracts_table.setRowCount(0)
            self.rename_tag_button.setEnabled(False)
            self.delete_tag_button.setEnabled(False)
            self.remove_tag_button.setEnabled(False)
            return
        
        # Get selected tag
        item = selected_items[0]
        tag_id = item.data(Qt.ItemDataRole.UserRole)
        self.selected_tag_id = tag_id
        
        # Update UI
        self._update_tag_statistics(tag_id)
        self._load_tag_documents(tag_id)
        self._load_tag_extracts(tag_id)
        
        # Enable buttons
        self.rename_tag_button.setEnabled(True)
        self.delete_tag_button.setEnabled(True)
        self.remove_tag_button.setEnabled(True)
    
    @pyqtSlot(QPoint)
    def _on_tag_context_menu(self, pos):
        """Show context menu for tag list."""
        item = self.tag_list.itemAt(pos)
        if not item:
            return
        
        tag_id = item.data(Qt.ItemDataRole.UserRole)
        tag_name = item.text()
        
        menu = QMenu(self)
        
        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(lambda: self._on_rename_tag(tag_id))
        
        menu.addSeparator()
        
        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(lambda: self._on_delete_tag(tag_id))
        
        menu.exec(self.tag_list.mapToGlobal(pos))
    
    @pyqtSlot()
    def _on_add_tag(self):
        """Handle add tag button click."""
        tag_name, ok = QInputDialog.getText(
            self, "Add Tag", "Enter tag name:"
        )
        
        if ok and tag_name:
            # Create tag
            tag = self.tag_manager.create_tag(tag_name)
            
            if tag:
                # Reload tags
                self._load_tags()
                
                # Select the new tag
                for i in range(self.tag_list.count()):
                    item = self.tag_list.item(i)
                    if item.data(Qt.ItemDataRole.UserRole) == tag.id:
                        item.setSelected(True)
                        break
            else:
                QMessageBox.warning(
                    self, "Error", 
                    f"Failed to create tag: {tag_name}"
                )
    
    @pyqtSlot(int)
    def _on_rename_tag(self, tag_id=None):
        """Handle rename tag button click."""
        if tag_id is None:
            tag_id = self.selected_tag_id
            
        if not tag_id:
            return
        
        tag = self.db_session.query(Tag).get(tag_id)
        if not tag:
            return
        
        new_name, ok = QInputDialog.getText(
            self, "Rename Tag", 
            "Enter new tag name:",
            text=tag.name
        )
        
        if ok and new_name:
            # Update tag
            tag.name = new_name
            self.db_session.commit()
            
            # Reload tags
            self._load_tags()
            
            # Update selected tag
            self._update_tag_statistics(tag_id)
    
    @pyqtSlot(int)
    def _on_delete_tag(self, tag_id=None):
        """Handle delete tag button click."""
        if tag_id is None:
            tag_id = self.selected_tag_id
            
        if not tag_id:
            return
        
        tag = self.db_session.query(Tag).get(tag_id)
        if not tag:
            return
        
        # Count documents and extracts with this tag
        doc_count = self.db_session.query(func.count(Document.id)).filter(
            Document.tags.any(Tag.id == tag_id)
        ).scalar() or 0
        
        extract_count = self.db_session.query(func.count(Extract.id)).filter(
            Extract.tags.any(Tag.id == tag_id)
        ).scalar() or 0
        
        # Confirmation dialog
        msg = f"Are you sure you want to delete tag '{tag.name}'?"
        
        if doc_count > 0 or extract_count > 0:
            msg += f"\n\nThis tag is used by {doc_count} documents and {extract_count} extracts."
        
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove tag from documents
            for doc in tag.documents:
                doc.tags.remove(tag)
            
            # Remove tag from extracts
            for extract in tag.extracts:
                extract.tags.remove(tag)
            
            # Delete tag
            self.db_session.delete(tag)
            self.db_session.commit()
            
            # Reload tags
            self._load_tags()
            
            # Clear selection
            self.selected_tag_id = None
            self.tag_stats_label.setText("No tag selected")
            self.documents_table.setRowCount(0)
            self.extracts_table.setRowCount(0)
            self.rename_tag_button.setEnabled(False)
            self.delete_tag_button.setEnabled(False)
            self.remove_tag_button.setEnabled(False)
    
    @pyqtSlot()
    def _on_merge_tags(self):
        """Handle merge tags button click."""
        # Get all tags
        tags = self.tag_manager.get_all_tags()
        tag_names = [tag.name for tag in tags]
        
        # First tag selection
        tag1_name, ok1 = QInputDialog.getItem(
            self, "Merge Tags", 
            "Select first tag:",
            tag_names, 0, False
        )
        
        if not ok1:
            return
        
        # Second tag selection
        tag2_name, ok2 = QInputDialog.getItem(
            self, "Merge Tags", 
            "Select second tag:",
            tag_names, 0, False
        )
        
        if not ok2 or tag1_name == tag2_name:
            return
        
        # Target tag selection
        target_name, ok3 = QInputDialog.getText(
            self, "Merge Tags", 
            "Enter name for merged tag:",
            text=f"{tag1_name}-{tag2_name}"
        )
        
        if not ok3:
            return
        
        # Find tags
        tag1 = next((tag for tag in tags if tag.name == tag1_name), None)
        tag2 = next((tag for tag in tags if tag.name == tag2_name), None)
        
        if not tag1 or not tag2:
            QMessageBox.warning(
                self, "Error", 
                "One or both selected tags not found."
            )
            return
        
        # Create new tag or find existing
        target_tag = self.tag_manager.create_tag(target_name)
        
        if not target_tag:
            QMessageBox.warning(
                self, "Error", 
                f"Failed to create target tag: {target_name}"
            )
            return
        
        # Move all tagged items from tag1 and tag2 to target_tag
        try:
            # Add documents from tag1
            for doc in tag1.documents:
                if target_tag not in doc.tags:
                    doc.tags.append(target_tag)
            
            # Add documents from tag2
            for doc in tag2.documents:
                if target_tag not in doc.tags:
                    doc.tags.append(target_tag)
            
            # Add extracts from tag1
            for extract in tag1.extracts:
                if target_tag not in extract.tags:
                    extract.tags.append(target_tag)
            
            # Add extracts from tag2
            for extract in tag2.extracts:
                if target_tag not in extract.tags:
                    extract.tags.append(target_tag)
            
            # Delete original tags if they're different from target
            if tag1.id != target_tag.id:
                self.db_session.delete(tag1)
            
            if tag2.id != target_tag.id:
                self.db_session.delete(tag2)
            
            self.db_session.commit()
            
            # Reload tags
            self._load_tags()
            
            # Select the new tag
            for i in range(self.tag_list.count()):
                item = self.tag_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == target_tag.id:
                    item.setSelected(True)
                    break
            
            QMessageBox.information(
                self, "Tags Merged", 
                f"Tags merged successfully into '{target_name}'."
            )
            
        except Exception as e:
            logger.exception(f"Error merging tags: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to merge tags: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_export_tags(self):
        """Handle export tags button click."""
        try:
            # Get all tags
            tags = self.tag_manager.get_all_tags()
            
            # Create export text
            export_text = "# Incrementum Tags Export\n\n"
            
            for tag in tags:
                export_text += f"## {tag.name}\n\n"
                
                # Count documents and extracts
                doc_count = len(tag.documents)
                extract_count = len(tag.extracts)
                
                export_text += f"* Documents: {doc_count}\n"
                export_text += f"* Extracts: {extract_count}\n\n"
                
                # Document list
                if doc_count > 0:
                    export_text += "### Documents\n\n"
                    for doc in tag.documents:
                        export_text += f"* {doc.title}\n"
                    export_text += "\n"
                
                # Extract list (first 5 only to avoid huge exports)
                if extract_count > 0:
                    export_text += "### Extracts (first 5)\n\n"
                    for i, extract in enumerate(tag.extracts[:5]):
                        content = extract.content
                        if len(content) > 100:
                            content = content[:97] + "..."
                        export_text += f"* {content}\n"
                    
                    if extract_count > 5:
                        export_text += f"* ...and {extract_count - 5} more extracts\n"
                    
                    export_text += "\n"
            
            # Copy to clipboard
            QApplication.clipboard().setText(export_text)
            
            QMessageBox.information(
                self, "Tags Exported", 
                "Tag export copied to clipboard in Markdown format."
            )
            
        except Exception as e:
            logger.exception(f"Error exporting tags: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to export tags: {str(e)}"
            )
    
    @pyqtSlot(QPoint)
    def _on_document_context_menu(self, pos):
        """Show context menu for document table."""
        index = self.documents_table.indexAt(pos)
        if not index.isValid():
            return
        
        document_id = self.documents_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        
        open_action = menu.addAction("Open Document")
        open_action.triggered.connect(lambda: self.itemSelected.emit("document", document_id))
        
        menu.addSeparator()
        
        remove_tag_action = menu.addAction("Remove Tag")
        remove_tag_action.triggered.connect(lambda: self._remove_tag_from_document(document_id))
        
        menu.exec(self.documents_table.viewport().mapToGlobal(pos))
    
    @pyqtSlot(QPoint)
    def _on_extract_context_menu(self, pos):
        """Show context menu for extract table."""
        index = self.extracts_table.indexAt(pos)
        if not index.isValid():
            return
        
        extract_id = self.extracts_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        
        open_action = menu.addAction("Open Extract")
        open_action.triggered.connect(lambda: self.itemSelected.emit("extract", extract_id))
        
        menu.addSeparator()
        
        remove_tag_action = menu.addAction("Remove Tag")
        remove_tag_action.triggered.connect(lambda: self._remove_tag_from_extract(extract_id))
        
        menu.exec(self.extracts_table.viewport().mapToGlobal(pos))
    
    @pyqtSlot(QModelIndex)
    def _on_document_selected(self, index):
        """Handle document selection (double-click)."""
        if not index.isValid():
            return
        
        document_id = self.documents_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit("document", document_id)
    
    @pyqtSlot(QModelIndex)
    def _on_extract_selected(self, index):
        """Handle extract selection (double-click)."""
        if not index.isValid():
            return
        
        extract_id = self.extracts_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit("extract", extract_id)
    
    @pyqtSlot()
    def _on_remove_tag_from_selected(self):
        """Remove tag from selected document or extract."""
        # Check which tab is active
        tab_index = self.extracts_tab.parentWidget().currentIndex()
        
        if tab_index == 0:
            # Documents tab
            selected_rows = self.documents_table.selectedItems()
            if not selected_rows:
                return
            
            row = selected_rows[0].row()
            document_id = self.documents_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self._remove_tag_from_document(document_id)
            
        elif tab_index == 1:
            # Extracts tab
            selected_rows = self.extracts_table.selectedItems()
            if not selected_rows:
                return
            
            row = selected_rows[0].row()
            extract_id = self.extracts_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self._remove_tag_from_extract(extract_id)
    
    def _remove_tag_from_document(self, document_id):
        """Remove the selected tag from a document."""
        if not self.selected_tag_id:
            return
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self, "Confirm Remove", 
            "Remove this tag from the selected document?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove tag
            if self.tag_manager.remove_document_tag(document_id, self.selected_tag_id):
                # Reload documents
                self._load_tag_documents(self.selected_tag_id)
                # Update statistics
                self._update_tag_statistics(self.selected_tag_id)
            else:
                QMessageBox.warning(
                    self, "Error", 
                    "Failed to remove tag from document."
                )
    
    def _remove_tag_from_extract(self, extract_id):
        """Remove the selected tag from an extract."""
        if not self.selected_tag_id:
            return
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self, "Confirm Remove", 
            "Remove this tag from the selected extract?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove tag
            if self.tag_manager.remove_extract_tag(extract_id, self.selected_tag_id):
                # Reload extracts
                self._load_tag_extracts(self.selected_tag_id)
                # Update statistics
                self._update_tag_statistics(self.selected_tag_id)
            else:
                QMessageBox.warning(
                    self, "Error", 
                    "Failed to remove tag from extract."
                )