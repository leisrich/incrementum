# ui/models/document_model.py

from PyQt6.QtCore import Qt, QAbstractListModel, QModelIndex, QVariant
from sqlalchemy.orm import Session
from core.knowledge_base.models import Document, Category

class DocumentModel(QAbstractListModel):
    """Model for displaying documents in a list view."""
    
    def __init__(self, db_session: Session):
        super().__init__()
        
        self.db_session = db_session
        self.documents = []
        self.category_id = None
        
        # Load documents
        self._reload_documents()
    
    def rowCount(self, parent=QModelIndex()):
        """Return the number of rows in the model."""
        return len(self.documents)
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return data for the given index and role."""
        if not index.isValid() or index.row() >= len(self.documents):
            return QVariant()
        
        document = self.documents[index.row()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return document.title
        elif role == Qt.ItemDataRole.ToolTipRole:
            return f"{document.title}\nAuthor: {document.author}\nImported: {document.imported_date}"
        
        return QVariant()
    
    def set_category_filter(self, category_id: int = None):
        """Filter documents by category."""
        self.category_id = category_id
        self._reload_documents()
    
    def get_document_id(self, index):
        """Get document ID for the given index."""
        if not index.isValid() or index.row() >= len(self.documents):
            return None
        
        return self.documents[index.row()].id
    
    def _reload_documents(self):
        """Reload documents from the database."""
        self.beginResetModel()
        
        query = self.db_session.query(Document)
        
        if self.category_id is not None:
            query = query.filter(Document.category_id == self.category_id)
        
        self.documents = query.order_by(Document.last_accessed.desc()).all()
        
        self.endResetModel()
