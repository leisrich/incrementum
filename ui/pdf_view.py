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
    pageChangeRequest = pyqtSignal(int)  # New signal for page change
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.pixmap = None
        self.zoom_factor = 1.0
        self.page = None
        self.doc = None
        self.highlights = {}  # Dictionary mapping page numbers to highlight rectangles
        self.current_highlights = []  # Temporary highlights for current selection
        self.selected_text = ""
        self.text_page = None  # TextPage for the current page
        self.current_page_num = 0
        self.total_pages = 0
        self.visible_pos = (0, 0)  # Track visible position (top-left corner)
        
        # Set focus policy to receive keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        
        # Set minimum size
        self.setMinimumSize(600, 800)
        
        # Initialize mouse tracking variables
        self.is_selecting = False
        self.selection_start = None
        self.selection_end = None
        
        # For panning support
        self.is_panning = False
        self.pan_start = None
        
        # Setup scroll area
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.layout().addWidget(self.scroll_area)
        
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.content_widget)
    
    def get_visible_position(self):
        """Get the current visible position in the document."""
        if hasattr(self, 'scroll_area'):
            # Get scroll position
            h_scroll = self.scroll_area.horizontalScrollBar().value()
            v_scroll = self.scroll_area.verticalScrollBar().value()
            return (h_scroll, v_scroll)
        return (0, 0)  # Default
        
    def set_visible_position(self, position):
        """Set the visible position in the document."""
        if not position or not hasattr(self, 'scroll_area'):
            return
            
        try:
            x, y = position
            
            # Get scroll bars
            h_scroll = self.scroll_area.horizontalScrollBar()
            v_scroll = self.scroll_area.verticalScrollBar()
            
            # Set position with bounds checking
            if h_scroll.maximum() >= x:
                h_scroll.setValue(int(x))
            
            if v_scroll.maximum() >= y:
                v_scroll.setValue(int(y))
                
            # Store for later reference
            self.visible_pos = (h_scroll.value(), v_scroll.value())
            
        except Exception as e:
            logger.error(f"Error setting visible position: {e}")
    
    def set_page(self, doc, page_number):
        """Set the current page to display."""
        self.doc = doc
        self.total_pages = len(doc) if doc else 0
        self.current_page_num = page_number
        
        if 0 <= page_number < self.total_pages:
            self.page = doc[page_number]
            self.render_page()
            self.update()
            
            # Reset visible position when changing pages
            self.visible_pos = (0, 0)
            if hasattr(self, 'scroll_area'):
                self.scroll_area.horizontalScrollBar().setValue(0)
                self.scroll_area.verticalScrollBar().setValue(0)
    
    def set_zoom(self, zoom_factor):
        """Set the zoom factor."""
        # Store current visible center for re-centering after zoom
        if hasattr(self, 'scroll_area'):
            h_scroll = self.scroll_area.horizontalScrollBar()
            v_scroll = self.scroll_area.verticalScrollBar()
            
            # Calculate center point of current view
            viewport_width = self.scroll_area.viewport().width()
            viewport_height = self.scroll_area.viewport().height()
            
            center_x = h_scroll.value() + viewport_width / 2
            center_y = v_scroll.value() + viewport_height / 2
            
            # Calculate relative position (0-1)
            if self.pixmap:
                rel_x = center_x / self.pixmap.width()
                rel_y = center_y / self.pixmap.height()
            else:
                rel_x, rel_y = 0.5, 0.5
        
        # Apply zoom
        old_zoom = self.zoom_factor
        self.zoom_factor = zoom_factor
        
        if self.page:
            self.render_page()
            self.update()
            
            # Re-center view after zoom
            if hasattr(self, 'scroll_area') and self.pixmap:
                # Calculate new center point
                new_center_x = rel_x * self.pixmap.width()
                new_center_y = rel_y * self.pixmap.height()
                
                # Calculate new scroll position
                new_h_scroll = new_center_x - viewport_width / 2
                new_v_scroll = new_center_y - viewport_height / 2
                
                # Set scroll position with bounds checking
                h_scroll.setValue(max(0, int(new_h_scroll)))
                v_scroll.setValue(max(0, int(new_v_scroll)))
                
                # Update visible position
                self.visible_pos = (h_scroll.value(), v_scroll.value())
    
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
        
        # If we're using a scroll area approach
        if hasattr(self, 'content_widget') and hasattr(self, 'content_layout'):
            # Clear current content
            for i in reversed(range(self.content_layout.count())):
                item = self.content_layout.itemAt(i)
                if item.widget():
                    item.widget().deleteLater()
            
            # Create label to display the pixmap
            pixmap_label = QLabel()
            pixmap_label.setPixmap(self.pixmap)
            pixmap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Add to layout
            self.content_layout.addWidget(pixmap_label)
            
            # Set fixed size on content widget to ensure scrollbars appear
            self.content_widget.setFixedSize(self.pixmap.width(), self.pixmap.height())
        else:
            # Original approach - direct display
            # Update widget size
            self.setMinimumSize(self.pixmap.size())
            self.resize(self.pixmap.size())
        
        # Generate text page for text extraction
        self.text_page = self.page.get_textpage()
        
        # Save the visible position to restore it later if needed
        if hasattr(self, 'scroll_area'):
            h_scroll = self.scroll_area.horizontalScrollBar()
            v_scroll = self.scroll_area.verticalScrollBar()
            self.visible_pos = (h_scroll.value(), v_scroll.value())
    
    def paintEvent(self, event):
        """Paint the widget."""
        # If we're using a scroll area approach, don't override paint event
        if hasattr(self, 'content_widget') and hasattr(self, 'content_layout'):
            super().paintEvent(event)
            return
            
        # Original direct painting approach for backward compatibility
        if not self.pixmap:
            return
        
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)
        
        # Draw saved highlights for current page
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 0, 80)))  # Yellow with transparency
        
        # Get highlights for current page
        if self.current_page_num in self.highlights:
            for highlight in self.highlights[self.current_page_num]:
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
        # Initialize page highlights if not exists
        if self.current_page_num not in self.highlights:
            self.highlights[self.current_page_num] = []
            
        if text is None:
            # Use current selection
            self.highlights[self.current_page_num].extend(self.current_highlights)
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
                self.highlights[self.current_page_num].append(screen_rect)
        
        self.update()
    
    def clear_highlights(self):
        """Clear all highlights on current page."""
        if self.current_page_num in self.highlights:
            self.highlights[self.current_page_num] = []
        self.update()
    
    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming and page navigation."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom with Ctrl+Wheel
            delta = event.angleDelta().y()
            if delta > 0:
                self.set_zoom(min(3.0, self.zoom_factor + 0.1))
            else:
                self.set_zoom(max(0.5, self.zoom_factor - 0.1))
            event.accept()
        else:
            # Page navigation with wheel
            delta = event.angleDelta().y()
            if delta < 0 and self.current_page_num < self.total_pages - 1:
                # Scroll down = next page
                self.pageChangeRequest.emit(self.current_page_num + 1)
                event.accept()
            elif delta > 0 and self.current_page_num > 0:
                # Scroll up = previous page
                self.pageChangeRequest.emit(self.current_page_num - 1)
                event.accept()
            else:
                super().wheelEvent(event)
    
    def keyPressEvent(self, event):
        """Handle keyboard navigation."""
        if event.key() == Qt.Key.Key_Down or event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_Space:
            if self.current_page_num < self.total_pages - 1:
                self.pageChangeRequest.emit(self.current_page_num + 1)
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Up or event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_Backspace:
            if self.current_page_num > 0:
                self.pageChangeRequest.emit(self.current_page_num - 1)
                event.accept()
                return
        
        super().keyPressEvent(event)


class PDFViewWidget(QWidget):
    """Widget for displaying and interacting with PDF documents."""
    
    extractCreated = pyqtSignal(int)
    
    def __init__(self, document: Document, db_session):
        super().__init__()
        
        self.document = document
        self.db_session = db_session
        self.content_text = ""
        
        # Create extractor
        self.extractor = ContentExtractor(db_session)
        
        # Track current page
        self.current_page = 0
        self.doc = None
        self.total_pages = 0
        
        # Create UI
        self._create_ui()
        
        # Load the PDF document
        self._load_pdf()
        
        # Track view state for position restoration
        self.saved_state = {
            "page": 0,
            "zoom_factor": 1.0,
            "position": (0, 0)  # x, y coordinates
        }
        
        # Restore position from document if available
        self._restore_position()
    
    def get_view_state(self):
        """Get the current view state for saving."""
        state = {
            "page": self.current_page,
            "zoom_factor": self.pdf_view.zoom_factor if hasattr(self.pdf_view, 'zoom_factor') else 1.0,
        }
        
        # Get any additional position info
        if hasattr(self.pdf_view, 'get_visible_position'):
            state["position"] = self.pdf_view.get_visible_position()
            
        return state
    
    def set_view_state(self, state):
        """Restore view state from saved state."""
        try:
            # Restore page
            if "page" in state and state["page"] != self.current_page:
                if self.doc and 0 <= state["page"] < len(self.doc):
                    self.current_page = state["page"]
                    self.page_spin.setValue(self.current_page + 1)
                    self.pdf_view.set_page(self.doc, self.current_page)
            
            # Restore zoom
            if "zoom_factor" in state and hasattr(self.pdf_view, 'set_zoom'):
                self.pdf_view.set_zoom(state["zoom_factor"])
                
            # Restore position within page if available
            if "position" in state and hasattr(self.pdf_view, 'set_visible_position'):
                self.pdf_view.set_visible_position(state["position"])
                
        except Exception as e:
            logger.exception(f"Error restoring PDF view state: {e}")
            
    def _save_position(self):
        """Save the current reading position."""
        try:
            # Check if we have a document to save position for
            if not self.document:
                return
                
            # Get current page
            page_position = f"page:{self.current_page}"
            
            # Get zoom factor if available
            if hasattr(self.pdf_view, 'zoom_factor'):
                page_position += f";zoom:{self.pdf_view.zoom_factor}"
                
            # Get scroll position if available
            scroll_pos = None
            if hasattr(self.pdf_view, 'get_visible_position'):
                pos = self.pdf_view.get_visible_position()
                if pos:
                    page_position += f";pos:{pos[0]},{pos[1]}"
            
            # Update the document
            self.document.position = page_position
            self.db_session.commit()
            
            logger.debug(f"Saved PDF position: {page_position}")
            
        except Exception as e:
            logger.exception(f"Error saving PDF position: {e}")
    
    def _restore_position(self):
        """Restore the last reading position."""
        try:
            if not self.document:
                return
                
            # Get stored position string
            position_str = getattr(self.document, 'position', None)
            if not position_str:
                logger.info(f"No stored position found for {self.document.title}")
                return
                
            logger.info(f"Restoring position from: {position_str}")
            
            # Parse position string (format: page:1;zoom:1.2;pos:100,200)
            parts = position_str.split(';')
            
            # Process each part
            for part in parts:
                if not part:
                    continue
                    
                if ':' not in part:
                    continue
                    
                key, value = part.split(':', 1)
                
                if key == 'page':
                    try:
                        page = int(value)
                        if self.doc and 0 <= page < len(self.doc):
                            self.current_page = page
                            self.page_spin.setValue(page + 1)
                            self.pdf_view.set_page(self.doc, page)
                    except ValueError:
                        pass
                        
                elif key == 'zoom' and hasattr(self.pdf_view, 'set_zoom'):
                    try:
                        zoom = float(value)
                        self.pdf_view.set_zoom(zoom)
                        # Update the combo box too
                        self._update_zoom_combo(zoom)
                    except ValueError:
                        pass
                        
                elif key == 'pos' and hasattr(self.pdf_view, 'set_visible_position'):
                    try:
                        x, y = map(float, value.split(','))
                        self.pdf_view.set_visible_position((x, y))
                    except (ValueError, TypeError):
                        pass
                
            logger.info(f"Restored PDF position: page {self.current_page} for {self.document.title}")
                
        except Exception as e:
            logger.exception(f"Error restoring PDF position: {e}")
            
    def _update_zoom_combo(self, zoom_factor):
        """Update the zoom combo box to match the current zoom factor."""
        if hasattr(self, 'zoom_combo'):
            # Find the closest match in the combo box
            zoom_percent = int(zoom_factor * 100)
            index = self.zoom_combo.findText(f"{zoom_percent}%")
            if index >= 0:
                self.zoom_combo.setCurrentIndex(index)
            else:
                # Add a custom zoom level if it doesn't exist
                self.zoom_combo.addItem(f"{zoom_percent}%")
                index = self.zoom_combo.findText(f"{zoom_percent}%")
                self.zoom_combo.setCurrentIndex(index)
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Toolbar
        toolbar = QToolBar()
        
        # Page navigation
        self.prev_page_action = QAction("Previous Page", self)
        self.prev_page_action.setShortcut(QKeySequence("PgUp"))
        self.prev_page_action.triggered.connect(self._on_prev_page)
        toolbar.addAction(self.prev_page_action)
        
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(len(self.doc) if self.doc else 1)
        self.page_spin.setValue(self.current_page + 1)
        self.page_spin.valueChanged.connect(self._on_page_changed)
        toolbar.addWidget(self.page_spin)
        
        self.page_label = QLabel(f" of {len(self.doc) if self.doc else 1}")
        toolbar.addWidget(self.page_label)
        
        self.next_page_action = QAction("Next Page", self)
        self.next_page_action.setShortcut(QKeySequence("PgDown"))
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
        self.pdf_view.pageChangeRequest.connect(self._on_page_requested)
        
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
        
        # Make splitter handle more visible and user-friendly
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        
        main_layout.addWidget(splitter)
    
    def _load_pdf(self):
        """Load the PDF document."""
        try:
            file_path = self.document.file_path
            
            # Check if file exists
            if not os.path.isfile(file_path):
                logger.error(f"PDF file not found: {file_path}")
                
                # Try alternative file path if in temporary directory
                if '/tmp/' in file_path:
                    # Check if the file was moved or renamed
                    tmp_dir = os.path.dirname(file_path)
                    if os.path.exists(tmp_dir):
                        files = os.listdir(tmp_dir)
                        pdf_files = [f for f in files if f.endswith('.pdf')]
                        if pdf_files:
                            new_path = os.path.join(tmp_dir, pdf_files[0])
                            logger.info(f"Using alternative PDF file found in the same directory: {new_path}")
                            file_path = new_path
                            
                            # Update the document's file_path
                            self.document.file_path = file_path
                            self.db_session.commit()
                        else:
                            logger.error(f"No PDF files found in {tmp_dir}")
                            raise FileNotFoundError(f"PDF file not found: {file_path}")
                    else:
                        logger.error(f"Temporary directory not found: {tmp_dir}")
                        raise FileNotFoundError(f"PDF file not found: {file_path}")
                else:
                    raise FileNotFoundError(f"PDF file not found: {file_path}")
            
            # Try loading with PyMuPDF
            try:
                # Open the PDF document
                self.doc = fitz.open(file_path)
                self.total_pages = len(self.doc)
                
                # Set initial page
                if self.total_pages > 0:
                    self.page_spin.setMaximum(self.total_pages)
                    self.page_label.setText(f" of {self.total_pages}")
                    
                    # Set the first page initially
                    self.pdf_view.set_page(self.doc, 0)
                
                logger.info(f"Loaded PDF with PyMuPDF: {file_path} with {self.total_pages} pages")
            except Exception as mupdf_error:
                # If PyMuPDF fails, try using QtPdf as a fallback
                logger.warning(f"PyMuPDF failed to load PDF: {mupdf_error}. Trying QPdfView fallback.")
                
                try:
                    from PyQt6.QtPdf import QPdfDocument
                    from PyQt6.QtPdfWidgets import QPdfView
                    
                    # Remove the old PDF view
                    self.pdf_view.setParent(None)
                    self.pdf_view.deleteLater()
                    
                    # Create a new layout for the QPdfView
                    layout = QVBoxLayout()
                    container = QWidget()
                    container.setLayout(layout)
                    
                    # Create QPdfView
                    pdf_qt_view = QPdfView()
                    
                    # Create PDF document
                    pdf_document = QPdfDocument()
                    
                    # Load the PDF file
                    pdf_document.load(file_path)
                    
                    # Set the document to the view
                    pdf_qt_view.setDocument(pdf_document)
                    
                    # Add to layout
                    layout.addWidget(pdf_qt_view)
                    
                    # Replace the PDF view with QPdfView
                    self.content_layout.addWidget(container)
                    
                    # Disable the UI elements that won't work with QPdfView
                    self.extract_action.setEnabled(False)
                    self.bookmark_action.setEnabled(False)
                    
                    # Add a notice about limited functionality
                    notice = QLabel("Limited functionality mode: Extract creation disabled")
                    notice.setStyleSheet("background-color: #FFF3CD; padding: 5px; border: 1px solid #FFEEBA;")
                    self.toolbar_layout.addWidget(notice)
                    
                    logger.info(f"Loaded PDF with QPdfView fallback: {file_path}")
                except ImportError:
                    # If QPdfView is not available, reraise the original error
                    logger.error("QPdfView fallback not available. PDF cannot be displayed.")
                    raise mupdf_error
                except Exception as qt_error:
                    # If QPdfView also fails, show both errors
                    logger.exception(f"Both PDF viewers failed. PyMuPDF error: {mupdf_error}, QPdfView error: {qt_error}")
                    raise Exception(f"Failed to load PDF with both viewers. PyMuPDF error: {mupdf_error}, QPdfView error: {qt_error}")
                
        except Exception as e:
            logger.exception(f"Error loading PDF: {e}")
            QMessageBox.warning(self, "Error", f"Error loading PDF: {str(e)}")
    
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
            self.extractCreated.emit(extract.id)
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

    @pyqtSlot(int)
    def _on_page_requested(self, page_number):
        """Handle page change request from PDF view."""
        if self.doc and 0 <= page_number < len(self.doc):
            self.current_page = page_number
            self.page_spin.setValue(self.current_page + 1)
            self.pdf_view.set_page(self.doc, self.current_page)

    def closeEvent(self, event):
        """Handle widget close event to save position."""
        self._save_position()
        super().closeEvent(event)
