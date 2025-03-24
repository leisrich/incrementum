# ui/models/category_model.py

from PyQt6.QtCore import Qt, QAbstractItemModel, QModelIndex, QVariant
from sqlalchemy.orm import Session
from core.knowledge_base.models import Category

class CategoryModel(QAbstractItemModel):
    """Model for displaying hierarchical categories in a tree view."""
    
    def __init__(self, db_session: Session):
        super().__init__()
        
        self.db_session = db_session
        self.categories = []
        self.category_map = {}  # Map from category ID to index in the categories list
        self.parent_map = {}  # Map from category ID to parent ID
        
        # Load categories
        self._reload_categories()
    
    def index(self, row, column, parent=QModelIndex()):
        """Create an index for the given row, column and parent."""
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        
        if not parent.isValid():
            # Top-level categories
            parent_id = None
        else:
            # Get the parent category ID
            parent_category = self.categories[parent.internalId()]
            parent_id = parent_category.id
        
        # Find the child category
        children = [c for c in self.categories if c.parent_id == parent_id]
        if row < len(children):
            child = children[row]
            return self.createIndex(row, column, self.category_map[child.id])
        
        return QModelIndex()
    
    def parent(self, index):
        """Return the parent of the given index."""
        if not index.isValid():
            return QModelIndex()
        
        category = self.categories[index.internalId()]
        if category.parent_id is None:
            return QModelIndex()
        
        # Get the parent category
        parent_id = category.parent_id
        parent_index = self.category_map.get(parent_id)
        if parent_index is None:
            return QModelIndex()
        
        # Get the parent's parent ID
        parent_category = self.categories[parent_index]
        parent_parent_id = parent_category.parent_id
        
        # Find the row of the parent in its parent's children
        if parent_parent_id is None:
            # Parent is a top-level category
            parent_siblings = [c for c in self.categories if c.parent_id is None]
        else:
            # Parent has a parent
            parent_siblings = [c for c in self.categories if c.parent_id == parent_parent_id]
        
        for i, sibling in enumerate(parent_siblings):
            if sibling.id == parent_id:
                return self.createIndex(i, 0, parent_index)
        
        return QModelIndex()
    
    def rowCount(self, parent=QModelIndex()):
        """Return the number of rows under the given parent."""
        if parent.column() > 0:
            return 0
        
        if not parent.isValid():
            # Top-level categories
            return len([c for c in self.categories if c.parent_id is None])
        
        # Get the parent category
        parent_category = self.categories[parent.internalId()]
        
        # Count children
        return len([c for c in self.categories if c.parent_id == parent_category.id])
    
    def columnCount(self, parent=QModelIndex()):
        """Return the number of columns in the model."""
        return 1
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return data for the given index and role."""
        if not index.isValid():
            return QVariant()
        
        category = self.categories[index.internalId()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return category.name
        elif role == Qt.ItemDataRole.ToolTipRole:
            return category.description or category.name
        
        return QVariant()
    
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Return the header data for the given section, orientation and role."""
        if (orientation == Qt.Orientation.Horizontal and 
            role == Qt.ItemDataRole.DisplayRole and 
            section == 0):
            return "Categories"
        
        return QVariant()
    
    def flags(self, index):
        """Return the item flags for the given index."""
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    
    def get_category_id(self, index):
        """Get category ID for the given index."""
        if not index.isValid():
            return None
        
        category = self.categories[index.internalId()]
        return category.id
    
    def _reload_categories(self):
        """Reload categories from the database."""
        self.beginResetModel()
        
        # Load all categories
        self.categories = self.db_session.query(Category).all()
        
        # Build maps
        self.category_map = {category.id: i for i, category in enumerate(self.categories)}
        self.parent_map = {category.id: category.parent_id for category in self.categories}
        
        # Update user categories in settings
        try:
            from core.utils.category_helper import update_user_categories
            update_user_categories(self.db_session)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to update user categories in settings: {e}")
        
        self.endResetModel()
