# ui/pdf_view.py

import os
import logging
import tempfile
import fitz  # PyMuPDF
from typing import Dict, Any, List, Tuple, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox, QSlider, QComboBox,
    QSpinBox, QCheckBox, QGroupBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QRectF, QPointF, QSizeF
from PyQt6.QtGui import (
    QAction, QPixmap, QPainter, QColor, QPen, QBrush, 
    QImage, QKeySequence, QCursor
)

from core.knowledge_base.models import Document, Extract
from core.content_extractor.extractor import ContentExtractor

logger = logging.getLogger(__name__)

class PDFGraphicsView(QWidget):
    """Custom widget for displaying PDF pages with highlighting and annotation."""
    
    selectionChanged = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.pixmap = None
        self.zoom_factor = 1.0
        self.page = None
        self.doc = None
        self.highlights = []  # List of highlight rectangles (QRectF)
        self.current_highlights = []  # Temporary highlights for current selection
        self.selected_text = ""
        self.text_page = None  # TextPage for the current page
        
        # Set focus policy to receive keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        
        # Set minimum size
        self.setMinimumSize(600, 800)
        
        # Initialize mouse tracking variables
        self.is_selecting = False
        self.selection_start = None
        self.selection_end = None
    
    def set_page(self, doc, page_number):
        """Set the current page to display."""
        self.doc = doc
        if 0 <= page_number < len(doc):
            self.page = doc[page_number]
            self.render_page()
            self.update()
    
    def set_zoom(self, zoom_factor):
        """Set the zoom factor."""
        self.zoom_factor = zoom_factor
        if self.page:
            self.render_page()
            self.update()
    
    def render_page(self):
        """Render the current page with current zoom level."""
        if not self.page:
            return
        
        # Get page dimensions
        zoom_matrix = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pix = self.page.get_pixmap(matrix=zoom_matrix, alpha=False)
        
        # Convert to QPixmap
        img_data = pix.samples
        img = QImage(img_data, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        self.pixmap = QPixmap.fromImage(img)
        
        # Update widget size
        self.setMinimumSize(self.pixmap.size())
        self.resize(self.pixmap.size())
        
        # Generate text page for text extraction
        self.text_page = self.page.get_textpage()
    
    def paintEvent(self, event):
        """Paint the widget."""
        if not self.pixmap:
            return
        
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)
        
        # Draw saved highlights
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 0, 80)))  # Yellow with transparency
        
        for highlight in self.highlights:
            painter.drawRect(highlight)
        
        # Draw current selection
        painter.setBrush(QBrush(QColor(0, 120, 215, 80)))  # Blue with transparency
        
        for highlight in self.current_highlights:
            painter.drawRect(highlight)
    
    def mousePressEvent(self, event):
        """Handle mouse press events."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_selecting = True
            self.selection_start = event.position()
            self.selection_end = event.position()
            self.current_highlights = []
            self.selected_text = ""
            self.update()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move events."""
        if self.is_selecting:
            self.selection_end = event.position()
            self._update_selection()
            self.update()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release events."""
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.selection_end = event.position()
            self._update_selection()
            self.update()
            
            # Emit signal with selected text
            if self.selected_text:
                self.selectionChanged.emit(self.selected_text)
    
    def _update_selection(self):
        """Update selection based on current mouse positions."""
        if not self.page or not self.text_page:
            return
        
        # Convert screen coordinates to page coordinates
        p1 = QPointF(self.selection_start.x(), self.selection_start.y())
        p2 = QPointF(self.selection_end.x(), self.selection_end.y())
        
        # Create rectangle from points
        rect = QRectF(p1, p2).normalized()
        
        # Scale back to original page coordinates
        page_rect = QRectF(
            rect.x() / self.zoom_factor,
            rect.y() / self.zoom_factor,
            rect.width() / self.zoom_factor,
            rect.height() / self.zoom_factor
        )
        
        # Extract text from this region
        fitz_rect = fitz.Rect(
            page_rect.x(), page_rect.y(), 
            page_rect.x() + page_rect.width(), 
            page_rect.y() + page_rect.height()
        )
        
        self.selected_text = self.page.get_text("text", clip=fitz_rect)
        
        # Get text spans in this region for more accurate highlighting
        spans = self.page.get_text("dict", clip=fitz_rect)["blocks"]
        
        # Clear current highlights
        self.current_highlights = []
        
        # Create highlight rectangles
        for block in spans:
            if block["type"] == 0:  # Text block
                for line in block["lines"]:
                    for span in line["spans"]:
                        span_rect = fitz.Rect(span["bbox"])
                        # Convert back to screen coordinates
                        screen_rect = QRectF(
                            span_rect.x0 * self.zoom_factor,
                            span_rect.y0 * self.zoom_factor,
                            (span_rect.x1 - span_rect.x0) * self.zoom_factor,
                            (span_rect.y1 - span_rect.y0) * self.zoom_factor
                        )
                        self.current_highlights.append(screen_rect)

    def add_highlight(self, text=None):
        """Add current selection to permanent highlights."""
        if text is None:
            # Use current selection
            self.highlights.extend(self.current_highlights)
        else:
            # Highlight specific text
            instances = self.page.search_for(text)
            for inst in instances:
                # Convert to screen coordinates
                screen_rect = QRectF(
                    inst.x0 * self.zoom_factor,
                    inst.y0 * self.zoom_factor,
                    (inst.x1 - inst.x0) * self.zoom_factor,
                    (inst.y1 - inst.y0) * self.zoom_factor
                )
                self.highlights.append(screen_rect)
        
        self.update()
    
    def clear_highlights(self):
        """Clear all highlights."""
        self.highlights = []
        self.update()
    
    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom with Ctrl+Wheel
            delta = event.angleDelta().y()
            if delta > 0:
                self.set_zoom(min(3.0, self.zoom_factor + 0.1))
            else:
                self.set_zoom(max(0.5, self.zoom_factor - 0.1))
            event.accept()
        else:
            # Otherwise, let the parent handle scrolling
            super().wheelEvent(event)


class PDFViewWidget(QWidget):
    """Widget for displaying and interacting with PDF documents."""
    
    extractCreated = pyqtSignal(Extract)
    
    def __init__(self, document: Document, db_session):
        super().__init__()
        
        self.document = document
        self.db_session = db_session
        self.extractor = ContentExtractor(db_session)
        
        self.doc = None
        self.current_page = 0
        self.extracts = []
        self.bookmarks = []
        
        # Load the PDF
        self._load_pdf()
        
        # Set up UI
        self._create_ui()
        
        # Load existing extracts and bookmarks
        self._load_extracts()
        self._load_bookmarks()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QToolBar()
        
        # Page navigation
        self.prev_page_action = QAction("Previous Page", self)
        self.prev_page_action.setShortcut(QKeySequence.MoveToPreviousPage)
        self.prev_page_action.triggered.connect(self._on_prev_page)
        toolbar.addAction(self.prev_page_action)
        
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(len(self.doc) if self.doc else 1)
        self.page_spin.setValue(self.current_page + 1)
        self.page_spin.valueChanged.connect(self._on_page_changed)
        toolbar.addWidget(self.page_spin)
        
        self.page_count_label = QLabel(f" / {len(self.doc) if self.doc else 1}")
        toolbar.addWidget(self.page_count_label)
        
        self.next_page_action = QAction("Next Page", self)
        self.next_page_action.setShortcut(QKeySequence.MoveToNextPage)
        self.next_page_action.triggered.connect(self._on_next_page)
        toolbar.addAction(self.next_page_action)
        
        toolbar.addSeparator()
        
        # Zoom controls
        zoom_label = QLabel("Zoom:")
        toolbar.addWidget(zoom_label)
        
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "300%"])
        self.zoom_combo.setCurrentText("100%")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.zoom_combo)
        
        toolbar.addSeparator()
        
        # Extract actions
        self.extract_action = QAction("Create Extract", self)
        self.extract_action.setEnabled(False)
        self.extract_action.triggered.connect(self._on_create_extract)
        toolbar.addAction(self.extract_action)
        
        self.bookmark_action = QAction("Add Bookmark", self)
        self.bookmark_action.triggered.connect(self._on_add_bookmark)
        toolbar.addAction(self.bookmark_action)
        
        main_layout.addWidget(toolbar)
        
        # Main content area
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # PDF view
        pdf_container = QWidget()
        pdf_layout = QVBoxLayout(pdf_container)
        pdf_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create scroll area for PDF view
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        # Create PDF view widget
        self.pdf_view = PDFGraphicsView()
        self.pdf_view.selectionChanged.connect(self._on_selection_changed)
        
        # Set initial page
        if self.doc:
            self.pdf_view.set_page(self.doc, self.current_page)
        
        scroll_area.setWidget(self.pdf_view)
        pdf_layout.addWidget(scroll_area)
        
        # Sidebar for extracts and bookmarks
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        
        # Extracts group
        extracts_group = QGroupBox("Extracts")
        extracts_layout = QVBoxLayout(extracts_group)
        
        self.extracts_list = QTextEdit()
        self.extracts_list.setReadOnly(True)
        extracts_layout.addWidget(self.extracts_list)
        
        # Bookmarks group
        bookmarks_group = QGroupBox("Bookmarks")
        bookmarks_layout = QVBoxLayout(bookmarks_group)
        
        self.bookmarks_list = QTextEdit()
        self.bookmarks_list.setReadOnly(True)
        bookmarks_layout.addWidget(self.bookmarks_list)
        
        # Add groups to sidebar
        sidebar_layout.addWidget(extracts_group)
        sidebar_layout.addWidget(bookmarks_group)
        
        # Add widgets to splitter
        splitter.addWidget(sidebar)
        splitter.addWidget(pdf_container)
        splitter.setStretchFactor(0, 1)  # Sidebar
        splitter.setStretchFactor(1, 3)  # PDF view
        
        main_layout.addWidget(splitter)
    
    def _load_pdf(self):
        """Load the PDF document."""
        try:
            if os.path.exists(self.document.file_path):
                self.doc = fitz.open(self.document.file_path)
                logger.info(f"Loaded PDF with {len(self.doc)} pages")
            else:
                logger.error(f"PDF file not found: {self.document.file_path}")
                QMessageBox.warning(
                    self, "Error", f"PDF file not found: {self.document.file_path}"
                )
                self.doc = None
        except Exception as e:
            logger.exception(f"Error loading PDF: {e}")
            QMessageBox.warning(
                self, "Error", f"Error loading PDF: {str(e)}"
            )
            self.doc = None
    
    def _load_extracts(self):
        """Load existing extracts for this document."""
        self.extracts = self.db_session.query(Extract).filter(
            Extract.document_id == self.document.id
        ).all()
        
        self._update_extracts_list()
    
    def _load_bookmarks(self):
        """Load bookmarks for this document."""
        # In a real app, bookmarks would be stored in the database
        # For now, just use a placeholder
        self.bookmarks = []
        self._update_bookmarks_list()
    
    def _update_extracts_list(self):
        """Update the extracts list display."""
        text = ""
        for extract in self.extracts:
            text += f"<b>Priority: {extract.priority}</b><br>"
            text += f"{extract.content[:100]}...<br>"
            text += f"<i>Created: {extract.created_date}</i><br>"
            text += "-" * 40 + "<br><br>"
        
        if not text:
            text = "No extracts yet"
        
        self.extracts_list.setHtml(text)
    
    def _update_bookmarks_list(self):
        """Update the bookmarks list display."""
        text = ""
        for bookmark in self.bookmarks:
            text += f"<b>Page {bookmark['page']+1}</b><br>"
            text += f"{bookmark['text']}<br>"
            text += "-" * 40 + "<br><br>"
        
        if not text:
            text = "No bookmarks yet"
        
        self.bookmarks_list.setHtml(text)
    
    @pyqtSlot()
    def _on_prev_page(self):
        """Go to previous page."""
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.page_spin.setValue(self.current_page + 1)
            self.pdf_view.set_page(self.doc, self.current_page)
    
    @pyqtSlot()
    def _on_next_page(self):
        """Go to next page."""
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.page_spin.setValue(self.current_page + 1)
            self.pdf_view.set_page(self.doc, self.current_page)
    
    @pyqtSlot(int)
    def _on_page_changed(self, page_number):
        """Handle page change from spin box."""
        if self.doc and 1 <= page_number <= len(self.doc):
            self.current_page = page_number - 1
            self.pdf_view.set_page(self.doc, self.current_page)
    
    @pyqtSlot(str)
    def _on_zoom_changed(self, zoom_text):
        """Handle zoom change."""
        try:
            zoom_factor = float(zoom_text.rstrip('%')) / 100.0
            self.pdf_view.set_zoom(zoom_factor)
        except ValueError:
            pass
    
    @pyqtSlot(str)
    def _on_selection_changed(self, selected_text):
        """Handle text selection changes."""
        self.extract_action.setEnabled(bool(selected_text))
    
    @pyqtSlot()
    def _on_create_extract(self):
        """Create an extract from selected text."""
        selected_text = self.pdf_view.selected_text
        if not selected_text:
            return
        
        # Highlight in PDF view
        self.pdf_view.add_highlight()
        
        # Get position info
        position = f"page:{self.current_page+1}"
        
        # Create extract
        extract = self.extractor.create_extract(
            document_id=self.document.id,
            content=selected_text,
            context=f"Page {self.current_page+1}",
            position=position,
            priority=50  # Default priority
        )
        
        if extract:
            # Reload extracts
            self._load_extracts()
            
            # Emit signal
            self.extractCreated.emit(extract)
        else:
            QMessageBox.warning(
                self, "Extract Creation Failed", 
                "Failed to create extract"
            )
    
    @pyqtSlot()
    def _on_add_bookmark(self):
        """Add a bookmark for the current page."""
        # In a real app, we'd show a dialog to enter bookmark title
        # For now, just use a simple approach
        
        # Add to bookmarks
        self.bookmarks.append({
            'page': self.current_page,
            'text': f"Bookmark on page {self.current_page+1}"
        })
        
        # Update display
        self._update_bookmarks_list()
