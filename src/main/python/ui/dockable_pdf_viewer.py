# ui/dockable_pdf_view.py

import logging
from PyQt6.QtWidgets import QDockWidget, QWidget, QVBoxLayout, QToolBar, QAction, QMenu
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QIcon

from .pdf_view import PDFViewWidget
from core.knowledge_base.models import Document, Extract

logger = logging.getLogger(__name__)

class DockablePDFView(QDockWidget):
    """A dockable wrapper for the PDF viewer widget."""
    
    extractCreated = pyqtSignal(Extract)
    
    def __init__(self, document: Document, db_session, parent=None):
        """
        Initialize the dockable PDF viewer.
        
        Args:
            document: Document object to display
            db_session: Database session
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.document = document
        self.db_session = db_session
        
        # Set window properties
        self.setWindowTitle(f"PDF: {document.title}")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable | 
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        
        # Create content widget
        self.content_widget = QWidget()
        self.setWidget(self.content_widget)
        
        # Create layout
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Add dock controls toolbar
        self.dock_toolbar = QToolBar()
        self.dock_toolbar.setIconSize(QSize(16, 16))
        
        # Add docking actions
        self.action_float = QAction("Float Window", self)
        self.action_float.triggered.connect(self._on_float)
        self.dock_toolbar.addAction(self.action_float)
        
        self.action_dock_left = QAction("Dock Left", self)
        self.action_dock_left.triggered.connect(lambda: self._on_dock(Qt.DockWidgetArea.LeftDockWidgetArea))
        self.dock_toolbar.addAction(self.action_dock_left)
        
        self.action_dock_right = QAction("Dock Right", self)
        self.action_dock_right.triggered.connect(lambda: self._on_dock(Qt.DockWidgetArea.RightDockWidgetArea))
        self.dock_toolbar.addAction(self.action_dock_right)
        
        self.action_dock_bottom = QAction("Dock Bottom", self)
        self.action_dock_bottom.triggered.connect(lambda: self._on_dock(Qt.DockWidgetArea.BottomDockWidgetArea))
        self.dock_toolbar.addAction(self.action_dock_bottom)
        
        layout.addWidget(self.dock_toolbar)
        
        # Create and add PDF viewer
        self.pdf_viewer = PDFViewWidget(document, db_session)
        self.pdf_viewer.extractCreated.connect(self._on_extract_created)
        layout.addWidget(self.pdf_viewer)
        
        # Context menu for title bar
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
    
    @pyqtSlot()
    def _on_float(self):
        """Float the dock widget as a separate window."""
        self.setFloating(True)
    
    @pyqtSlot(Qt.DockWidgetArea)
    def _on_dock(self, area):
        """
        Dock the widget to a specific area.
        
        Args:
            area: The dock area to dock to
        """
        if self.parent():
            self.parent().addDockWidget(area, self)
            self.setFloating(False)
    
    @pyqtSlot(Extract)
    def _on_extract_created(self, extract):
        """Forward the extract created signal."""
        self.extractCreated.emit(extract)
    
    @pyqtSlot(QPoint)
    def _show_context_menu(self, pos):
        """Show context menu for the dock widget."""
        menu = QMenu(self)
        
        # Add actions
        menu.addAction(self.action_float)
        menu.addSeparator()
        menu.addAction(self.action_dock_left)
        menu.addAction(self.action_dock_right)
        menu.addAction(self.action_dock_bottom)
        
        menu.exec(self.mapToGlobal(pos))
