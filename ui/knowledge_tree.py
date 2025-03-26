"""
Knowledge tree view for categorizing documents.
"""

import logging
from PyQt6.QtCore import (
    Qt, pyqtSignal, QModelIndex, QMimeData, QByteArray, QDataStream, QIODevice
)
from PyQt6.QtWidgets import QTreeView, QAbstractItemView
from PyQt6.QtGui import QStandardItemModel, QStandardItem

from core.knowledge_base.interface import (
    get_all_categories, get_category_by_id, create_category, 
    assign_document_to_category, remove_document_from_category
)

logger = logging.getLogger(__name__)

class KnowledgeTree(QTreeView):
    """
    Tree view for displaying and managing knowledge categories.
    """
    
    category_selected = pyqtSignal(int)  # Signal emitted when a category is selected
    
    def __init__(self, parent=None, db_session=None):
        super().__init__(parent)
        self.db_session = db_session
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        
        # Flag to identify this as a knowledge tree for drag and drop operations
        self.is_knowledge_tree = True
        
        # Setup model
        self._setup_model()
        
        # Connect signals
        self.selectionModel().selectionChanged.connect(self._on_selection_changed)
    
    def set_db_session(self, session):
        """Set the database session for the tree."""
        self.db_session = session
        self.model().set_db_session(session)
        self.refresh_tree()
    
    def _setup_model(self):
        """Set up the tree model."""
        self.tree_model = CategoryTreeModel(self.db_session)
        self.setModel(self.tree_model)
        
        # Set column widths
        self.setColumnWidth(0, 200)  # Name column
        self.setColumnWidth(1, 80)   # Document count column
        
        # Enable sorting
        self.setSortingEnabled(True)
        
    def refresh_tree(self):
        """Refresh the tree data."""
        try:
            self.tree_model.load_categories()
            self.expandAll()  # Expand all categories by default
        except Exception as e:
            logger.exception(f"Error refreshing knowledge tree: {e}")
    
    def _on_selection_changed(self, selected, deselected):
        """Handle selection changes in the tree."""
        try:
            indexes = selected.indexes()
            if indexes:
                index = indexes[0]  # Get the first selected index
                category_id = self.model().data(index, Qt.ItemDataRole.UserRole)
                if category_id:
                    self.category_selected.emit(category_id)
        except Exception as e:
            logger.exception(f"Error handling category selection: {e}")

    def dragEnterEvent(self, event):
        """Handle drag enter events."""
        if event.mimeData().hasFormat("application/x-documentitem"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
    
    def dragMoveEvent(self, event):
        """Handle drag move events."""
        if event.mimeData().hasFormat("application/x-documentitem"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
    
    def dropEvent(self, event):
        """Handle drop events for documents."""
        try:
            if event.mimeData().hasFormat("application/x-documentitem"):
                # Get the index where the item was dropped
                drop_index = self.indexAt(event.pos())
                if drop_index.isValid():
                    # Process the drop using the model
                    self.model().handleDocumentDrop(event.mimeData(), drop_index)
                    event.acceptProposedAction()
            else:
                super().dropEvent(event)
        except Exception as e:
            logger.exception(f"Error handling drop event: {e}")

class CategoryTreeModel(QStandardItemModel):
    """
    Model for the knowledge category tree.
    """
    
    def __init__(self, db_session=None):
        super().__init__()
        self.db_session = db_session
        self.setHorizontalHeaderLabels(["Category", "Documents"])
        self.is_knowledge_tree = True  # Flag to identify this as a knowledge tree model
        
        # Load categories if session is available
        if db_session:
            self.load_categories()
    
    def set_db_session(self, session):
        """Set the database session for the model."""
        self.db_session = session
    
    def load_categories(self):
        """Load all categories from the database."""
        if not self.db_session:
            logger.warning("No database session available for loading categories")
            return
            
        try:
            # Clear current items
            self.clear()
            self.setHorizontalHeaderLabels(["Category", "Documents"])
            
            # Get all categories from the database
            categories = get_all_categories(self.db_session)
            
            # Create a dictionary to store items by ID for fast lookup
            category_items = {}
            
            # First, create all category items
            for category in categories:
                item = QStandardItem(category['name'])
                item.setData(category['id'], Qt.ItemDataRole.UserRole)  # Store category ID for reference
                
                # Create document count item
                doc_count_item = QStandardItem(str(category.get('document_count', 0)))
                doc_count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                
                # Add both items to the row
                row = [item, doc_count_item]
                
                # Store in dictionary for building the tree
                category_items[category['id']] = row
                
                # If this is a root category (no parent), add directly to the model
                if not category['parent_id']:
                    self.appendRow(row)
                # Otherwise, find the parent and add as a child
                elif category['parent_id'] in category_items:
                    parent_row = category_items[category['parent_id']]
                    parent_item = parent_row[0]  # First column contains the category item
                    parent_item.appendRow(row)
                else:
                    # If parent not found yet, add to model root temporarily
                    # (This can happen if categories are loaded out of order)
                    self.appendRow(row)
            
            logger.debug(f"Loaded {len(categories)} categories into the tree")
        except Exception as e:
            logger.exception(f"Error loading categories: {e}")
    
    def handleDocumentDrop(self, mime_data, drop_index):
        """
        Handle documents being dropped onto a category.
        
        Args:
            mime_data: The mime data from the drop event
            drop_index: The model index where the drop occurred
        """
        try:
            # Get the category ID where the drop occurred
            category_item = self.itemFromIndex(drop_index)
            if not category_item:
                category_item = self.itemFromIndex(drop_index.parent())
                if not category_item:
                    logger.warning("No valid target category found for drop")
                    return
            
            category_id = category_item.data(Qt.ItemDataRole.UserRole)
            if not category_id:
                logger.warning("No category ID found for drop target")
                return
            
            # Extract document IDs from the mime data
            document_data = mime_data.data("application/x-documentitem")
            stream = QDataStream(document_data, QIODevice.OpenModeFlag.ReadOnly)
            document_ids = []
            while not stream.atEnd():
                document_id = stream.readInt32()
                document_ids.append(document_id)
            
            logger.debug(f"Documents dropped onto category {category_id}: {document_ids}")
            
            # Process each document ID
            for document_id in document_ids:
                # Assign document to category in the database
                from core.knowledge_base.interface import assign_document_to_category
                success = assign_document_to_category(document_id, category_id, self.db_session)
                
                if success:
                    logger.info(f"Document {document_id} assigned to category {category_id}")
                    
                    # Update document count for this category
                    doc_count_item = category_item.parent().child(category_item.row(), 1)
                    if doc_count_item:
                        current_count = int(doc_count_item.text() or 0)
                        doc_count_item.setText(str(current_count + 1))
                else:
                    logger.error(f"Failed to assign document {document_id} to category {category_id}")
            
        except Exception as e:
            logger.exception(f"Error handling document drop: {e}") 