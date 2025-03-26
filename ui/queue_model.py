"""
Model for the document reading queue.
"""

import logging
from PyQt6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, pyqtSignal, QMimeData, QByteArray, QDataStream, QIODevice
)
from PyQt6.QtGui import QColor

logger = logging.getLogger(__name__)

class QueueModel(QAbstractTableModel):
    """Model for displaying and managing documents in the reading queue."""
    
    # Signals
    dragDropSettingChanged = pyqtSignal(bool)
    itemDropped = pyqtSignal(object, object, list, QModelIndex)  # source_model, target_model, source_rows, target_index
    
    # Column definitions
    TITLE_COL = 0
    PRIORITY_COL = 1
    SOURCE_COL = 2
    DATE_COL = 3
    
    def __init__(self, db_session=None):
        super().__init__()
        self.db_session = db_session
        self.documents = []
        self.headers = ["Title", "Priority", "Source", "Imported Date"]
        self.drag_enabled = True
        
        if db_session:
            self.load_documents()
    
    def set_db_session(self, session):
        """Set the database session for the model."""
        self.db_session = session
        self.load_documents()
    
    def load_documents(self):
        """Load documents from the database."""
        if not self.db_session:
            logger.warning("No database session available for loading documents")
            return
            
        try:
            # Get documents in queue from the database
            from core.knowledge_base.models import Document
            documents = self.db_session.query(Document).filter(Document.in_queue == True).order_by(Document.queue_position).all()
            
            self.beginResetModel()
            self.documents = documents
            self.endResetModel()
            
            logger.debug(f"Loaded {len(documents)} documents into queue model")
        except Exception as e:
            logger.exception(f"Error loading documents: {e}")
    
    def rowCount(self, parent=QModelIndex()):
        """Return the number of rows in the model."""
        return len(self.documents)
    
    def columnCount(self, parent=QModelIndex()):
        """Return the number of columns in the model."""
        return len(self.headers)
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Return data for the specified index and role."""
        if not index.isValid() or index.row() >= len(self.documents):
            return None
            
        document = self.documents[index.row()]
        
        if role == Qt.ItemDataRole.DisplayRole:
            # Display data for each column
            if index.column() == self.TITLE_COL:
                return document.title
            elif index.column() == self.PRIORITY_COL:
                return document.priority if hasattr(document, 'priority') else "Normal"
            elif index.column() == self.SOURCE_COL:
                return document.source_url or "Local"
            elif index.column() == self.DATE_COL:
                return document.imported_date.strftime("%Y-%m-%d") if document.imported_date else ""
        
        elif role == Qt.ItemDataRole.UserRole:
            # Return document ID for reference
            return document.id
        
        elif role == Qt.ItemDataRole.ToolTipRole:
            # Tooltip with full info
            return f"Title: {document.title}\nSource: {document.source_url or 'Local'}\nImported: {document.imported_date}"
        
        return None
    
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Return header data for the specified section and orientation."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.headers[section]
        return None
    
    def flags(self, index):
        """Return item flags for the given index."""
        default_flags = super().flags(index)
        
        if not index.isValid():
            return default_flags
        
        # Add drag support if enabled
        if self.drag_enabled:
            return default_flags | Qt.ItemFlag.ItemIsDragEnabled
        
        return default_flags
    
    def mimeTypes(self):
        """Return the list of supported MIME types."""
        return ["application/x-documentitem"]
    
    def mimeData(self, indexes):
        """Return MIME data for the given indexes."""
        mime_data = QMimeData()
        encoded_data = QByteArray()
        
        stream = QDataStream(encoded_data, QIODevice.OpenModeFlag.WriteOnly)
        
        # Store the rows of the dragged items (using document IDs)
        rows = set()
        for index in indexes:
            if index.isValid() and index.column() == 0:  # Only consider the first column
                rows.add(index.row())
        
        # Write document IDs to the stream
        for row in rows:
            document_id = self.data(self.index(row, 0), Qt.ItemDataRole.UserRole)
            if document_id is not None:
                stream.writeInt32(document_id)
        
        mime_data.setData("application/x-documentitem", encoded_data)
        return mime_data
    
    def setDragEnabled(self, enabled):
        """Enable or disable drag support."""
        if self.drag_enabled != enabled:
            self.drag_enabled = enabled
            self.dragDropSettingChanged.emit(enabled)
    
    def dropMimeData(self, data, action, row, column, parent):
        """Handle dropping data onto the model."""
        if not data.hasFormat("application/x-documentitem"):
            return False
        
        if action == Qt.DropAction.IgnoreAction:
            return True
        
        # Get the drop position
        if row != -1:
            begin_row = row
        elif parent.isValid():
            begin_row = parent.row()
        else:
            begin_row = self.rowCount()
        
        # Extract document IDs from the mime data
        encoded_data = data.data("application/x-documentitem")
        stream = QDataStream(encoded_data, QIODevice.OpenModeFlag.ReadOnly)
        
        source_rows = []
        while not stream.atEnd():
            document_id = stream.readInt32()
            # Find the document's row in our model
            for i, doc in enumerate(self.documents):
                if doc.id == document_id:
                    source_rows.append(i)
                    break
        
        # Emit signal for external handling
        self.itemDropped.emit(self, self, source_rows, self.index(begin_row, 0))
        
        return True 
