# ui/pdf_view.py

import os
import logging
import tempfile
import fitz  # PyMuPDF
import re
from typing import Dict, Any, List, Tuple, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox, QSlider, QComboBox,
    QSpinBox, QCheckBox, QGroupBox, QFileDialog,
    QLineEdit, QDialog, QProgressBar, QInputDialog,
    QApplication, QProgressDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QRectF, QPointF, QSizeF, QTimer, QSize
from PyQt6.QtGui import (
    QAction, QPixmap, QPainter, QColor, QPen, QBrush, 
    QImage, QKeySequence, QCursor, QIcon, QFont, QShortcut,
    QActionGroup
)

from core.knowledge_base.models import Document, Extract
from core.content_extractor.extractor import ContentExtractor

logger = logging.getLogger(__name__)

class PDFSearchDialog(QDialog):
    """Dialog for searching text within a PDF."""
    
    def __init__(self, pdf_view, parent=None):
        super().__init__(parent)
        self.pdf_view = pdf_view
        self.search_results = []
        self.current_result = -1
        
        self.setWindowTitle("Search PDF")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Search input
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search text...")
        self.search_input.returnPressed.connect(self.start_search)
        search_layout.addWidget(self.search_input)
        
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.start_search)
        search_layout.addWidget(self.search_button)
        
        layout.addLayout(search_layout)
        
        # Options
        options_layout = QHBoxLayout()
        
        self.case_sensitive = QCheckBox("Case sensitive")
        options_layout.addWidget(self.case_sensitive)
        
        self.whole_words = QCheckBox("Whole words only")
        options_layout.addWidget(self.whole_words)
        
        layout.addLayout(options_layout)
        
        # Results navigation
        nav_layout = QHBoxLayout()
        
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self.go_to_previous)
        self.prev_button.setEnabled(False)
        nav_layout.addWidget(self.prev_button)
        
        self.next_button = QPushButton("Next")
        self.next_button.clicked.connect(self.go_to_next)
        self.next_button.setEnabled(False)
        nav_layout.addWidget(self.next_button)
        
        self.results_label = QLabel("No results")
        nav_layout.addWidget(self.results_label)
        
        layout.addLayout(nav_layout)
        
        # Close button
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        layout.addWidget(self.close_button)
    
    def start_search(self):
        """Start search with current input and options."""
        search_text = self.search_input.text()
        if not search_text:
            return
            
        self.search_results = []
        self.current_result = -1
        
        # Show progress dialog for long documents
        progress = QProgressBar(self)
        progress.setMinimum(0)
        progress.setMaximum(len(self.pdf_view.doc))
        progress.setValue(0)
        progress.setTextVisible(True)
        progress.setFormat("Searching page %v of %m")
        
        progress_dialog = QDialog(self)
        progress_dialog.setWindowTitle("Searching...")
        progress_layout = QVBoxLayout(progress_dialog)
        progress_layout.addWidget(progress)
        progress_dialog.setFixedSize(300, 100)
        progress_dialog.show()
        
        # Search the document
        try:
            for page_num in range(len(self.pdf_view.doc)):
                page = self.pdf_view.doc[page_num]
                
                # Get search options
                flags = 0
                if not self.case_sensitive.isChecked():
                    flags |= fitz.TEXT_PRESERVE_CASE
                if self.whole_words.isChecked():
                    flags |= fitz.TEXT_PRESERVE_WHITESPACE
                
                # Find all instances
                instances = page.search_for(search_text, flags=flags)
                
                for inst in instances:
                    self.search_results.append((page_num, inst))
                
                # Update progress
                progress.setValue(page_num + 1)
                QApplication.processEvents()
            
            # Close progress dialog
            progress_dialog.close()
            
            # Update UI
            if self.search_results:
                self.results_label.setText(f"Found {len(self.search_results)} results")
                self.next_button.setEnabled(True)
                self.prev_button.setEnabled(False)
                self.go_to_next()  # Go to first result
            else:
                self.results_label.setText("No results found")
                self.next_button.setEnabled(False)
                self.prev_button.setEnabled(False)
        
        except Exception as e:
            progress_dialog.close()
            logger.exception(f"Error during search: {e}")
            QMessageBox.warning(self, "Search Error", f"An error occurred during search: {str(e)}")
    
    def go_to_next(self):
        """Go to next search result."""
        if not self.search_results:
            return
            
        self.current_result = (self.current_result + 1) % len(self.search_results)
        self._go_to_current()
        
        # Update buttons
        self.prev_button.setEnabled(True)
        self.results_label.setText(f"Result {self.current_result + 1} of {len(self.search_results)}")
    
    def go_to_previous(self):
        """Go to previous search result."""
        if not self.search_results:
            return
            
        self.current_result = (self.current_result - 1) % len(self.search_results)
        self._go_to_current()
        
        # Update buttons
        self.next_button.setEnabled(True)
        self.results_label.setText(f"Result {self.current_result + 1} of {len(self.search_results)}")
    
    def _go_to_current(self):
        """Go to current search result."""
        if not self.search_results or self.current_result < 0:
            return
            
        page_num, rect = self.search_results[self.current_result]
        
        # Go to page if needed
        if self.pdf_view.current_page_num != page_num:
            self.pdf_view.set_page(self.pdf_view.doc, page_num)
            self.pdf_view.current_page = page_num
            
            # Update page spin box if available
            if hasattr(self.pdf_view, 'page_spin'):
                self.pdf_view.page_spin.setValue(page_num + 1)
        
        # Highlight the result
        self.pdf_view.highlight_search_result(rect)
        
        # Scroll to make it visible
        self.pdf_view.scroll_to_rect(rect)


class AnnotationToolbar(QToolBar):
    """Toolbar for annotation tools."""
    
    annotationChanged = pyqtSignal(str)  # Emits the current annotation type
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setIconSize(QSize(16, 16))
        self.current_tool = "select"
        self.current_color = QColor(255, 255, 0, 80)  # Default: Yellow with alpha
        
        # Add annotation tools
        self.select_action = QAction("Select", self)
        self.select_action.setCheckable(True)
        self.select_action.setChecked(True)
        self.select_action.triggered.connect(lambda: self._set_tool("select"))
        self.addAction(self.select_action)
        
        self.highlight_action = QAction("Highlight", self)
        self.highlight_action.setCheckable(True)
        self.highlight_action.triggered.connect(lambda: self._set_tool("highlight"))
        self.addAction(self.highlight_action)
        
        self.underline_action = QAction("Underline", self)
        self.underline_action.setCheckable(True)
        self.underline_action.triggered.connect(lambda: self._set_tool("underline"))
        self.addAction(self.underline_action)
        
        self.strikeout_action = QAction("Strikeout", self)
        self.strikeout_action.setCheckable(True)
        self.strikeout_action.triggered.connect(lambda: self._set_tool("strikeout"))
        self.addAction(self.strikeout_action)
        
        self.addSeparator()
        
        # Color picker
        self.color_combo = QComboBox()
        self.color_combo.addItem("Yellow", QColor(255, 255, 0, 80))
        self.color_combo.addItem("Green", QColor(0, 255, 0, 80))
        self.color_combo.addItem("Blue", QColor(0, 191, 255, 80))
        self.color_combo.addItem("Pink", QColor(255, 105, 180, 80))
        self.color_combo.addItem("Orange", QColor(255, 165, 0, 80))
        self.color_combo.currentIndexChanged.connect(self._on_color_changed)
        self.addWidget(self.color_combo)
        
        # Tool group to ensure only one is selected
        self.tool_group = QActionGroup(self)
        self.tool_group.addAction(self.select_action)
        self.tool_group.addAction(self.highlight_action)
        self.tool_group.addAction(self.underline_action)
        self.tool_group.addAction(self.strikeout_action)
        self.tool_group.setExclusive(True)
    
    def _set_tool(self, tool_name):
        """Set the current tool."""
        self.current_tool = tool_name
        self.annotationChanged.emit(tool_name)
    
    def _on_color_changed(self, index):
        """Handle color selection change."""
        self.current_color = self.color_combo.currentData()


class PDFGraphicsView(QWidget):
    """Enhanced widget for displaying PDF pages with highlighting and annotation."""
    
    selectionChanged = pyqtSignal(str)
    pageChangeRequest = pyqtSignal(int)
    navigate = pyqtSignal(str)  # For navigating between documents
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.pixmap = None
        self.zoom_factor = 1.5  # Start with slightly larger default zoom
        self.page = None
        self.doc = None
        self.highlights = {}  # Dictionary mapping page numbers to highlight rectangles
        self.current_highlights = []  # Temporary highlights for current selection
        self.selected_text = ""
        self.text_page = None
        self.current_page_num = 0
        self.total_pages = 0
        self.visible_pos = (0, 0)
        self.pixmap_label = None
        
        # Annotation properties
        self.annotations = {}  # Dictionary mapping page numbers to annotations
        self.current_tool = "select"
        self.annotation_color = QColor(255, 255, 0, 80)  # Default: Yellow with alpha
        
        # Continuous scrolling mode
        self.continuous_mode = True
        self.page_spacing = 20  # Pixels between pages in continuous mode
        
        # Search result highlighting
        self.search_highlight = None
        self.search_highlight_timer = QTimer(self)
        self.search_highlight_timer.timeout.connect(self._clear_search_highlight)
        self.search_highlight_timer.setSingleShot(True)
        
        # Set focus policy to receive keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        
        # Set minimum size
        self.setMinimumSize(800, 1000)
        
        # Initialize mouse tracking variables
        self.is_selecting = False
        self.selection_start = None
        self.selection_end = None
        self.is_panning = False
        self.pan_start = None
        
        # Setup layout and scroll area
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.layout().addWidget(self.scroll_area)
        
        self.content_widget = QWidget()
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area.setWidget(self.content_widget)
        
        # Install event filters
        self.scroll_area.viewport().installEventFilter(self)
    
    def set_continuous_mode(self, enabled):
        """Enable or disable continuous scrolling mode."""
        if self.continuous_mode != enabled:
            self.continuous_mode = enabled
            if self.doc and self.current_page_num >= 0:
                # Remember current page
                current_page = self.current_page_num
                # Re-render with new mode
                self.render_page()
                # If switching to continuous mode, scroll to current page
                if enabled:
                    self._scroll_to_page(current_page)
    
    def _scroll_to_page(self, page_num):
        """Scroll to make the specified page visible."""
        if not self.continuous_mode or not self.doc:
            return
            
        if 0 <= page_num < len(self.doc):
            # Calculate vertical position of the page
            y_pos = 0
            page_height = 0
            
            for i in range(page_num):
                # Get page height and add spacing
                page = self.doc[i]
                page_height = page.rect.height * self.zoom_factor
                y_pos += page_height + self.page_spacing
            
            # Set scrollbar position
            self.scroll_area.verticalScrollBar().setValue(int(y_pos))
    
    def get_visible_position(self):
        """Get the current visible position in the document."""
        if hasattr(self, 'scroll_area'):
            h_scroll = self.scroll_area.horizontalScrollBar().value()
            v_scroll = self.scroll_area.verticalScrollBar().value()
            return (h_scroll, v_scroll)
        return (0, 0)
        
    def set_visible_position(self, position):
        """Set the visible position in the document."""
        if not position or not hasattr(self, 'scroll_area'):
            return
            
        try:
            x, y = position
            
            h_scroll = self.scroll_area.horizontalScrollBar()
            v_scroll = self.scroll_area.verticalScrollBar()
            
            if h_scroll.maximum() >= x:
                h_scroll.setValue(int(x))
            
            if v_scroll.maximum() >= y:
                v_scroll.setValue(int(y))
                
            self.visible_pos = (h_scroll.value(), v_scroll.value())
            
        except Exception as e:
            logger.error(f"Error setting visible position: {e}")
    
    def highlight_search_result(self, rect):
        """Highlight a search result temporarily."""
        self.search_highlight = rect
        self.update()
        
        # Start timer to clear highlight after a period
        self.search_highlight_timer.start(3000)  # 3 seconds
    
    def _clear_search_highlight(self):
        """Clear the search highlight."""
        self.search_highlight = None
        self.update()
    
    def set_annotation_tool(self, tool_name):
        """Set the current annotation tool."""
        self.current_tool = tool_name
        
        # Update cursor based on tool
        if tool_name == "select":
            self.setCursor(Qt.CursorShape.ArrowCursor)
        elif tool_name in ["highlight", "underline", "strikeout"]:
            self.setCursor(Qt.CursorShape.IBeamCursor)
    
    def set_annotation_color(self, color):
        """Set the current annotation color."""
        self.annotation_color = color
    
    def scroll_to_rect(self, rect):
        """Scroll to make the specified rectangle visible."""
        if not self.scroll_area:
            return
            
        # Convert PDF coordinates to screen coordinates
        screen_rect = QRectF(
            rect.x0 * self.zoom_factor,
            rect.y0 * self.zoom_factor,
            (rect.x1 - rect.x0) * self.zoom_factor,
            (rect.y1 - rect.y0) * self.zoom_factor
        )
        
        # Get the viewport size
        viewport_width = self.scroll_area.viewport().width()
        viewport_height = self.scroll_area.viewport().height()
        
        # Calculate target scroll position to center the rect
        h_scroll = max(0, int(screen_rect.center().x() - viewport_width / 2))
        v_scroll = max(0, int(screen_rect.center().y() - viewport_height / 2))
        
        # Set scrollbar positions
        self.scroll_area.horizontalScrollBar().setValue(h_scroll)
        self.scroll_area.verticalScrollBar().setValue(v_scroll)
    
    def set_page(self, doc, page_number):
        """Set the current page to display."""
        self.doc = doc
        self.total_pages = len(doc) if doc else 0
        
        # In continuous mode, we still need to track current page
        self.current_page_num = page_number
        
        if 0 <= page_number < self.total_pages:
            if not self.continuous_mode:
                self.page = doc[page_number]
                self.render_page()
                self.update()
                
                # Reset visible position
                self.visible_pos = (0, 0)
                if hasattr(self, 'scroll_area'):
                    self.scroll_area.horizontalScrollBar().setValue(0)
                    self.scroll_area.verticalScrollBar().setValue(0)
            else:
                # In continuous mode, render all pages
                self.render_page()
                # Scroll to the current page
                self._scroll_to_page(page_number)
    
    def set_zoom(self, zoom_factor):
        """Set the zoom factor."""
        # Store current visible center for re-centering
        if hasattr(self, 'scroll_area'):
            h_scroll = self.scroll_area.horizontalScrollBar()
            v_scroll = self.scroll_area.verticalScrollBar()
            
            viewport_width = self.scroll_area.viewport().width()
            viewport_height = self.scroll_area.viewport().height()
            
            center_x = h_scroll.value() + viewport_width / 2
            center_y = v_scroll.value() + viewport_height / 2
            
            if self.pixmap:
                rel_x = center_x / self.pixmap.width()
                rel_y = center_y / self.pixmap.height()
            else:
                rel_x, rel_y = 0.5, 0.5
        
        # Apply zoom
        old_zoom = self.zoom_factor
        self.zoom_factor = zoom_factor
        
        # Remember current page in continuous mode
        current_page = self.current_page_num
        
        # Re-render
        self.render_page()
        self.update()
        
        # Re-center view or scroll to current page
        if hasattr(self, 'scroll_area'):
            if self.continuous_mode:
                # Scroll to current page
                self._scroll_to_page(current_page)
            elif self.pixmap:
                # Re-center view
                new_center_x = rel_x * self.pixmap.width()
                new_center_y = rel_y * self.pixmap.height()
                
                new_h_scroll = new_center_x - viewport_width / 2
                new_v_scroll = new_center_y - viewport_height / 2
                
                h_scroll.setValue(max(0, int(new_h_scroll)))
                v_scroll.setValue(max(0, int(new_v_scroll)))
                
                self.visible_pos = (h_scroll.value(), v_scroll.value())
    
    def render_page(self):
        """Render the current page(s) with current zoom level."""
        if not self.doc:
            return
        
        # Clear current content
        for i in reversed(range(self.content_layout.count())):
            item = self.content_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
        
        if self.continuous_mode:
            # Create a tall widget to hold all pages
            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)
            container_layout.setSpacing(self.page_spacing)
            
            # Calculate total height for all pages
            total_height = 0
            max_width = 0
            
            # Add page widgets
            for page_num in range(len(self.doc)):
                page = self.doc[page_num]
                
                # Create label for this page
                page_widget = self._render_single_page(page)
                container_layout.addWidget(page_widget)
                
                # Update size calculations
                total_height += page.rect.height * self.zoom_factor
                max_width = max(max_width, page.rect.width * self.zoom_factor)
                
                # Add spacing between pages
                if page_num < len(self.doc) - 1:
                    total_height += self.page_spacing
            
            # Set fixed size on container
            container.setFixedSize(int(max_width), int(total_height))
            
            # Add to layout
            self.content_layout.addWidget(container)
            self.content_widget.setFixedSize(container.size())
            
            # Store reference to all rendered pages
            self.rendered_pages = container
            
        else:
            # Single page mode - just render current page
            self.page = self.doc[self.current_page_num]
            
            # Generate the pixmap
            zoom_matrix = fitz.Matrix(self.zoom_factor, self.zoom_factor)
            pix = self.page.get_pixmap(matrix=zoom_matrix, alpha=False)
            
            # Convert to QPixmap
            img_data = pix.samples
            img = QImage(img_data, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            self.pixmap = QPixmap.fromImage(img)
            
            # Create label to display the pixmap
            self.pixmap_label = QLabel()
            self.pixmap_label.setPixmap(self.pixmap)
            self.pixmap_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # Add to layout
            self.content_layout.addWidget(self.pixmap_label)
            
            # Set fixed size on content widget to ensure scrollbars appear
            self.content_widget.setFixedSize(self.pixmap.width(), self.pixmap.height())
            
            # Generate text page for text extraction
            self.text_page = self.page.get_textpage()
        
        # Save the visible position
        if hasattr(self, 'scroll_area'):
            h_scroll = self.scroll_area.horizontalScrollBar()
            v_scroll = self.scroll_area.verticalScrollBar()
            self.visible_pos = (h_scroll.value(), v_scroll.value())
    
    def _render_single_page(self, page):
        """Render a single page to a widget."""
        zoom_matrix = fitz.Matrix(self.zoom_factor, self.zoom_factor)
        pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
        
        # Convert to QPixmap
        img_data = pix.samples
        img = QImage(img_data, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(img)
        
        # Create label to display the pixmap
        label = QLabel()
        label.setPixmap(pixmap)
        label.setFixedSize(pixmap.size())
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        return label
    
    def paintEvent(self, event):
        """Paint the widget."""
        super().paintEvent(event)

        if not self.current_highlights and not self.annotations and self.search_highlight is None:
            return  # Nothing to paint

        painter = QPainter(self)

        # Draw current selection
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 120, 215, 80)))  # Blue with transparency

        # Draw current selection
        for highlight in self.current_highlights:
            painter.drawRect(highlight)

        # Draw saved highlights for current page
        if self.current_page_num in self.highlights:
            painter.setBrush(QBrush(QColor(255, 255, 0, 80)))  # Yellow with transparency
            for highlight in self.highlights[self.current_page_num]:
                painter.drawRect(highlight)
        
        # Draw search result highlight if any
        if self.search_highlight:
            # Convert to screen coordinates and adjust for scroll
            h_scroll = self.scroll_area.horizontalScrollBar().value()
            v_scroll = self.scroll_area.verticalScrollBar().value()
            
            screen_rect = QRectF(
                self.search_highlight.x0 * self.zoom_factor - h_scroll,
                self.search_highlight.y0 * self.zoom_factor - v_scroll,
                (self.search_highlight.x1 - self.search_highlight.x0) * self.zoom_factor,
                (self.search_highlight.y1 - self.search_highlight.y0) * self.zoom_factor
            )
            
            # Draw with animated flashing effect
            flash_alpha = 128 + int(127 * abs(self.search_highlight_timer.remainingTime() % 1000 - 500) / 500)
            painter.setBrush(QBrush(QColor(255, 165, 0, flash_alpha)))  # Orange with variable transparency
            painter.drawRect(screen_rect)
    
    def eventFilter(self, watched, event):
        """Filter events to capture mouse events on the viewport."""
        if watched != self.scroll_area.viewport():
            return super().eventFilter(watched, event)

        # Handle mouse press
        if event.type() == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            # For selection tool
            if self.current_tool == "select":
                # Start selection
                self.is_selecting = True
                self.selection_start = event.position()
                self.selection_end = event.position()
                self.current_highlights = []
                self.selected_text = ""
                self.update()
                return True
            # For annotation tools
            elif self.current_tool in ["highlight", "underline", "strikeout"]:
                # Start annotation
                self.is_selecting = True
                self.selection_start = event.position()
                self.selection_end = event.position()
                self.current_highlights = []
                self.selected_text = ""
                self.update()
                return True

        # Handle mouse move during selection or annotation
        elif event.type() == event.Type.MouseMove and self.is_selecting:
            # Update selection end point
            self.selection_end = event.position()
            self._update_selection()
            self.update()
            return False  # Don't consume the event so scrolling still works

        # Handle mouse release
        elif event.type() == event.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            # Complete selection
            self.selection_end = event.position()
            self.is_selecting = False
            self._update_selection()
            
            # Apply annotations immediately if using an annotation tool
            if self.current_tool != "select" and self.selected_text:
                self._apply_annotation()
                
            self.update()
            return True

        # Let other events pass through
        return super().eventFilter(watched, event)
    
    def _apply_annotation(self):
        """Apply the current annotation to the selected text."""
        if not self.selected_text or self.current_tool == "select":
            return
            
        # Add to annotations list for current page
        if self.current_page_num not in self.annotations:
            self.annotations[self.current_page_num] = []
            
        # Add annotation with current tool and color
        for rect in self.current_highlights:
            annotation = {
                "type": self.current_tool,
                "rect": rect,
                "color": self.annotation_color
            }
            self.annotations[self.current_page_num].append(annotation)
            
        # Clear current highlights
        self.current_highlights = []
        self.update()
        
        # Add to highlights for permanent display
        if self.current_page_num not in self.highlights:
            self.highlights[self.current_page_num] = []
        
        # Get the rects and apply the appropriate color based on annotation type
        if self.current_tool == "highlight":
            color = self.annotation_color
        elif self.current_tool == "underline":
            color = QColor(0, 0, 255, 180)  # Blue for underline
        elif self.current_tool == "strikeout":
            color = QColor(255, 0, 0, 180)  # Red for strikeout
        
        # Apply in PyMuPDF if needed
        try:
            page = self.doc[self.current_page_num]
            
            # Get scroll position
            h_scroll = self.scroll_area.horizontalScrollBar().value()
            v_scroll = self.scroll_area.verticalScrollBar().value()
            
            # Convert screen coordinates back to PDF coordinates
            words = page.get_text("words")
            for word in words:
                word_rect = fitz.Rect(word[0:4])
                
                # Check if this word overlaps with selection
                screen_rect = QRectF(
                    word_rect.x0 * self.zoom_factor - h_scroll,
                    word_rect.y0 * self.zoom_factor - v_scroll,
                    (word_rect.x1 - word_rect.x0) * self.zoom_factor,
                    (word_rect.y1 - word_rect.y0) * self.zoom_factor
                )
                
                # Check for overlap with current selection
                # For simplicity, just add all recent screen rects
                self.highlights[self.current_page_num].append(screen_rect)
            
        except Exception as e:
            logger.warning(f"Error applying annotation in PyMuPDF: {e}")

    def _update_selection(self):
        """Update selection based on current mouse positions."""
        if not self.doc:
            return

        try:
            # Get scroll position
            h_scroll = self.scroll_area.horizontalScrollBar().value()
            v_scroll = self.scroll_area.verticalScrollBar().value()

            # Determine current page in continuous mode
            if self.continuous_mode:
                # Calculate which page the cursor is on
                total_height = 0
                for i in range(len(self.doc)):
                    page = self.doc[i]
                    page_height = page.rect.height * self.zoom_factor
                    
                    # Check if cursor is in this page's vertical range
                    if v_scroll + self.selection_start.y() >= total_height and v_scroll + self.selection_start.y() < total_height + page_height:
                        self.current_page_num = i
                        break
                        
                    total_height += page_height + self.page_spacing
            
            # Get the current page
            page = self.doc[self.current_page_num]

            # Convert screen coordinates to PDF coordinates, accounting for scroll and zoom
            start_x = (self.selection_start.x() + h_scroll) / self.zoom_factor
            start_y = (self.selection_start.y() + v_scroll) / self.zoom_factor
            end_x = (self.selection_end.x() + h_scroll) / self.zoom_factor
            end_y = (self.selection_end.y() + v_scroll) / self.zoom_factor

            # Create Fitz rectangle for text extraction
            fitz_rect = fitz.Rect(
                min(start_x, end_x),
                min(start_y, end_y),
                max(start_x, end_x),
                max(start_y, end_y)
            )

            # Extract text from this region
            try:
                # First try extracting as normal text
                self.selected_text = page.get_text("text", clip=fitz_rect)
                
                # If that doesn't work well, try with different options
                if not self.selected_text or len(self.selected_text.strip()) < 3:
                    # Try with different extraction modes
                    self.selected_text = page.get_text("blocks", clip=fitz_rect)
                    
                # Clean up text - remove excessive whitespace and newlines
                self.selected_text = re.sub(r'\s+', ' ', self.selected_text).strip()
                
            except Exception as e:
                logger.warning(f"Text extraction failed: {e}")
                self.selected_text = ""

            # Clear current highlights
            self.current_highlights = []

            # Get text spans for more precise highlighting
            try:
                # Get all words in the selection area
                words = page.get_text("words", clip=fitz_rect)
                
                # Create highlight rectangles for each word
                for word in words:
                    if len(word) >= 4:  # Each word entry should have at least x0,y0,x1,y1
                        word_rect = fitz.Rect(word[0:4])  # Extract the rectangle coordinates
                        
                        # Convert to screen coordinates for highlighting
                        screen_rect = QRectF(
                            word_rect.x0 * self.zoom_factor - h_scroll,
                            word_rect.y0 * self.zoom_factor - v_scroll,
                            (word_rect.x1 - word_rect.x0) * self.zoom_factor,
                            (word_rect.y1 - word_rect.y0) * self.zoom_factor
                        )
                        
                        self.current_highlights.append(screen_rect)
                
                # If word-level highlighting failed, fall back to using spans
                if len(self.current_highlights) == 0:
                    spans = page.get_text("dict", clip=fitz_rect).get("blocks", [])
                    
                    for block in spans:
                        if block.get("type", -1) == 0:  # Text block
                            for line in block.get("lines", []):
                                for span in line.get("spans", []):
                                    if "bbox" in span:
                                        span_rect = fitz.Rect(span["bbox"])
                                        
                                        # Convert to screen coordinates for highlighting
                                        screen_rect = QRectF(
                                            span_rect.x0 * self.zoom_factor - h_scroll,
                                            span_rect.y0 * self.zoom_factor - v_scroll,
                                            (span_rect.x1 - span_rect.x0) * self.zoom_factor,
                                            (span_rect.y1 - span_rect.y0) * self.zoom_factor
                                        )
                                        
                                        self.current_highlights.append(screen_rect)
                
            except Exception as e:
                # Fallback to simple rectangular highlight if span extraction fails
                logger.warning(f"Detailed highlighting failed, using rectangle: {e}")
                simple_rect = QRectF(
                    min(self.selection_start.x(), self.selection_end.x()),
                    min(self.selection_start.y(), self.selection_end.y()),
                    abs(self.selection_end.x() - self.selection_start.x()),
                    abs(self.selection_end.y() - self.selection_start.y())
                )
                self.current_highlights.append(simple_rect)

            # Emit signal if text was selected
            if self.selected_text:
                self.selectionChanged.emit(self.selected_text)

        except Exception as e:
            logger.exception(f"Error in _update_selection: {e}")
    
    def add_highlight(self, text=None):
        """Add current selection to permanent highlights."""
        try:
            # Initialize page highlights if not exists
            if self.current_page_num not in self.highlights:
                self.highlights[self.current_page_num] = []
                
            if text is None:
                # Use current selection
                self.highlights[self.current_page_num].extend(self.current_highlights)
            else:
                # Highlight specific text
                try:
                    instances = self.page.search_for(text)
                    
                    # Get scroll position
                    h_scroll = self.scroll_area.horizontalScrollBar().value()
                    v_scroll = self.scroll_area.verticalScrollBar().value()
                    
                    for inst in instances:
                        # Convert to screen coordinates
                        screen_rect = QRectF(
                            inst.x0 * self.zoom_factor - h_scroll,
                            inst.y0 * self.zoom_factor - v_scroll,
                            (inst.x1 - inst.x0) * self.zoom_factor,
                            (inst.y1 - inst.y0) * self.zoom_factor
                        )
                        self.highlights[self.current_page_num].append(screen_rect)
                except Exception as e:
                    logger.warning(f"Search-based highlighting failed: {e}")
            
            self.update()
        except Exception as e:
            logger.exception(f"Error adding highlight: {e}")
    
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
        elif not self.continuous_mode:
            # In single page mode, use wheel for page navigation
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
        else:
            # In continuous mode, handle normal scrolling
            super().wheelEvent(event)
    
    def keyPressEvent(self, event):
        """Handle keyboard navigation."""
        if event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_Space or event.key() == Qt.Key.Key_PageDown:
            if self.current_page_num < self.total_pages - 1:
                self.pageChangeRequest.emit(self.current_page_num + 1)
                event.accept()
            else:
                # If at last page, try to navigate to next document
                self.navigate.emit("next")
                event.accept()
            return
            
        elif event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_Backspace or event.key() == Qt.Key.Key_PageUp:
            if self.current_page_num > 0:
                self.pageChangeRequest.emit(self.current_page_num - 1)
                event.accept()
            else:
                # If at first page, try to navigate to previous document
                self.navigate.emit("previous")
                event.accept()
            return
        elif event.key() == Qt.Key.Key_N:
            # Navigate to next document
            self.navigate.emit("next")
            event.accept()
            return
        elif event.key() == Qt.Key.Key_P:
            # Navigate to previous document
            self.navigate.emit("previous")
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Home:
            # Go to first page
            self.pageChangeRequest.emit(0)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_End:
            # Go to last page
            self.pageChangeRequest.emit(self.total_pages - 1)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_F and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Open search dialog
            if hasattr(self, 'parent') and callable(self.parent):
                parent = self.parent()
                if hasattr(parent, 'open_search_dialog') and callable(parent.open_search_dialog):
                    parent.open_search_dialog()
            event.accept()
            return
        
        super().keyPressEvent(event)


class PDFViewWidget(QWidget):
    """Widget for displaying and interacting with PDF documents."""
    
    extractCreated = pyqtSignal(Extract)
    navigate = pyqtSignal(str)  # Add navigation signal
    
    def __init__(self, document: Document, db_session, parent=None):
        super().__init__(parent)
        
        self.document = document
        self.db_session = db_session
        self.content_text = ""
        
        # Create extractor
        from core.content_extractor.extractor import ContentExtractor
        self.extractor = ContentExtractor(db_session)
        
        # Track current page
        self.current_page = 0
        self.doc = None
        self.total_pages = 0
        
        # Initialize bookmarks and annotations
        self.bookmarks = []
        self.annotations = []
        
        # Create UI
        self._create_ui()
        
        # Load the PDF document
        self._load_pdf()
        
        # Load existing extracts and bookmarks
        self._load_extracts()
        self._load_bookmarks()
        
        # Track view state for position restoration
        self.saved_state = {
            "page": 0,
            "zoom_factor": 1.5,
            "position": (0, 0)
        }
        
        # Restore position from document if available
        self._restore_position()
        
        # Add shortcut keys
        self._setup_shortcuts()
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts."""
        # Search shortcut
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.open_search_dialog)
        
        # Print shortcut
        self.print_shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        self.print_shortcut.activated.connect(self._on_print)
        
        # Zoom shortcuts
        self.zoom_in_shortcut = QShortcut(QKeySequence("Ctrl++"), self)
        self.zoom_in_shortcut.activated.connect(self._on_zoom_in)
        
        self.zoom_out_shortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        self.zoom_out_shortcut.activated.connect(self._on_zoom_out)
        
        # Save page shortcuts
        self.save_page_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_page_shortcut.activated.connect(self._on_save_current_page)
    
    def open_search_dialog(self):
        """Open the search dialog."""
        search_dialog = PDFSearchDialog(self.pdf_view, self)
        search_dialog.show()
    
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
                self._update_zoom_combo(state["zoom_factor"])
                
            # Restore position within page if available
            if "position" in state and hasattr(self.pdf_view, 'set_visible_position'):
                self.pdf_view.set_visible_position(state["position"])
                
        except Exception as e:
            logger.exception(f"Error restoring PDF view state: {e}")
    
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
            
    def _save_position(self):
        """Save current position to document."""
        try:
            if not self.document:
                logger.warning("No document available for position saving")
                return
                
            # Get view state
            state = self.get_view_state()
            
            # Update document position with current page
            from core.knowledge_base.models import Document
            self.document.position = state.get('page', 0)
            
            # Store other state information as extra_info
            extra_info = {}
            if hasattr(self.document, 'extra_info') and self.document.extra_info:
                try:
                    import json
                    extra_info = json.loads(self.document.extra_info)
                except Exception as e:
                    logger.warning(f"Error parsing document extra_info: {e}")
                    extra_info = {}
            
            # Update PDF-specific state
            extra_info['pdf_state'] = state
            
            # Store updated extra_info
            import json
            self.document.extra_info = json.dumps(extra_info)
            
            # Update last accessed timestamp
            from datetime import datetime
            self.document.last_accessed = datetime.utcnow()
            
            # Commit changes
            self.db_session.commit()
            
            logger.info(f"Saved PDF state for document {self.document.id}: page={state.get('page', 0)}, zoom={state.get('zoom_factor', 1.0)}")
            
        except Exception as e:
            logger.exception(f"Error saving PDF position: {e}")
            
    def _restore_position(self):
        """Restore position from document."""
        try:
            if not self.document:
                logger.warning("No document available for position restoration")
                return
                
            # Get basic position (page number)
            position = getattr(self.document, 'position', None)
            
            if position is None:
                logger.info(f"No stored position found for {self.document.title}")
                return
                
            # Create default state with page number
            state = {'page': int(position)}
            
            # Try to get more detailed state from extra_info
            if hasattr(self.document, 'extra_info') and self.document.extra_info:
                try:
                    import json
                    extra_info = json.loads(self.document.extra_info)
                    
                    # Check for PDF-specific saved state
                    if 'pdf_state' in extra_info:
                        pdf_state = extra_info['pdf_state']
                        # Update state with saved values
                        state.update(pdf_state)
                        logger.debug(f"Restored PDF state from extra_info: {pdf_state}")
                except Exception as e:
                    logger.warning(f"Error parsing document extra_info: {e}")
            
            # Apply the state
            self.set_view_state(state)
            
            # Verify restoration
            current_page = self.current_page
            if current_page == int(position):
                logger.info(f"Successfully restored position to page {position} for {self.document.title}")
            else:
                logger.warning(f"Position restoration verification failed. Expected page {position}, got {current_page}")
                
                # Try one more time with a delay
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(500, lambda: self._delayed_page_restore(int(position)))
                
        except Exception as e:
            logger.exception(f"Error restoring PDF position: {e}")
    
    def _delayed_page_restore(self, page):
        """Attempt page restoration again after a delay."""
        try:
            # Try to set the page
            if hasattr(self, 'pdf_view') and self.pdf_view:
                self.pdf_view.set_page(self.doc, page)
                
            # Update the page spin box if available
            if hasattr(self, 'page_spin'):
                self.page_spin.setValue(page + 1)  # +1 for 1-based display
                
            logger.debug(f"Attempted delayed restoration to page {page}")
        except Exception as e:
            logger.warning(f"Error in delayed page restoration: {e}")
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Main toolbar
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        
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
        self.zoom_combo.setCurrentText("150%")  # Set default zoom to 150%
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.zoom_combo)
        
        # Zoom in/out buttons
        self.zoom_in_action = QAction("Zoom In", self)
        self.zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        self.zoom_in_action.triggered.connect(self._on_zoom_in)
        toolbar.addAction(self.zoom_in_action)
        
        self.zoom_out_action = QAction("Zoom Out", self)
        self.zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self.zoom_out_action.triggered.connect(self._on_zoom_out)
        toolbar.addAction(self.zoom_out_action)
        
        toolbar.addSeparator()
        
        # View mode (single page / continuous)
        self.continuous_mode_check = QCheckBox("Continuous Mode")
        self.continuous_mode_check.setChecked(True)
        self.continuous_mode_check.stateChanged.connect(self._on_continuous_mode_changed)
        toolbar.addWidget(self.continuous_mode_check)
        
        toolbar.addSeparator()
        
        # Search
        self.search_action = QAction("Search", self)
        self.search_action.setShortcut(QKeySequence("Ctrl+F"))
        self.search_action.triggered.connect(self.open_search_dialog)
        toolbar.addAction(self.search_action)
        
        # Print/Export
        self.print_action = QAction("Print", self)
        self.print_action.setShortcut(QKeySequence("Ctrl+P"))
        self.print_action.triggered.connect(self._on_print)
        toolbar.addAction(self.print_action)
        
        # Save current page as image
        self.save_page_action = QAction("Save Page As...", self)
        self.save_page_action.triggered.connect(self._on_save_current_page)
        toolbar.addAction(self.save_page_action)
        
        # Extract action
        self.extract_action = QAction("Create Extract", self)
        self.extract_action.setEnabled(False)
        self.extract_action.triggered.connect(self._on_create_extract)
        toolbar.addAction(self.extract_action)
        
        main_layout.addWidget(toolbar)
        
        # Add annotation toolbar
        self.annotation_toolbar = AnnotationToolbar(self)
        self.annotation_toolbar.annotationChanged.connect(self._on_annotation_tool_changed)
        main_layout.addWidget(self.annotation_toolbar)
        
        # Main content area
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Sidebar for extracts and bookmarks
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        
        # Extracts group
        extracts_group = QGroupBox("Extracts")
        extracts_layout = QVBoxLayout(extracts_group)
        
        self.extracts_list = QTextEdit()
        self.extracts_list.setReadOnly(True)
        extracts_layout.addWidget(self.extracts_list)
        
        # Extract action buttons
        extract_buttons = QHBoxLayout()
        
        self.create_extract_button = QPushButton("Create Extract")
        self.create_extract_button.setEnabled(False)
        self.create_extract_button.clicked.connect(self._on_create_extract)
        extract_buttons.addWidget(self.create_extract_button)
        
        self.goto_extract_button = QPushButton("Go To Extract")
        self.goto_extract_button.setEnabled(False)
        self.goto_extract_button.clicked.connect(self._on_goto_extract)
        extract_buttons.addWidget(self.goto_extract_button)
        
        extracts_layout.addLayout(extract_buttons)
        
        # Bookmarks group
        bookmarks_group = QGroupBox("Bookmarks")
        bookmarks_layout = QVBoxLayout(bookmarks_group)
        
        self.bookmarks_list = QTextEdit()
        self.bookmarks_list.setReadOnly(True)
        bookmarks_layout.addWidget(self.bookmarks_list)
        
        # Bookmark action buttons
        bookmark_buttons = QHBoxLayout()
        
        self.add_bookmark_button = QPushButton("Add Bookmark")
        self.add_bookmark_button.clicked.connect(self._on_add_bookmark)
        bookmark_buttons.addWidget(self.add_bookmark_button)
        
        self.goto_bookmark_button = QPushButton("Go To Bookmark")
        self.goto_bookmark_button.setEnabled(False)
        self.goto_bookmark_button.clicked.connect(self._on_goto_bookmark)
        bookmark_buttons.addWidget(self.goto_bookmark_button)
        
        bookmarks_layout.addLayout(bookmark_buttons)
        
        # Add groups to sidebar
        sidebar_layout.addWidget(extracts_group)
        sidebar_layout.addWidget(bookmarks_group)
        
        # PDF view
        pdf_container = QWidget()
        pdf_layout = QVBoxLayout(pdf_container)
        pdf_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create enhanced PDF view widget
        self.pdf_view = PDFGraphicsView()
        self.pdf_view.selectionChanged.connect(self._on_selection_changed)
        self.pdf_view.pageChangeRequest.connect(self._on_page_requested)
        self.pdf_view.navigate.connect(self.navigate.emit)
        
        pdf_layout.addWidget(self.pdf_view)
        
        # Add widgets to splitter
        splitter.addWidget(sidebar)
        splitter.addWidget(pdf_container)
        splitter.setStretchFactor(0, 1)  # Sidebar
        splitter.setStretchFactor(1, 3)  # PDF view
        
        # Make splitter handle more visible and user-friendly
        splitter.setHandleWidth(8)
        splitter.setChildrenCollapsible(False)
        
        main_layout.addWidget(splitter)
        
        # Status bar
        status_bar = QWidget()
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(5, 2, 5, 2)
        
        self.status_label = QLabel("Ready")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch(1)
        
        self.page_info_label = QLabel("Page 1 of 1")
        status_layout.addWidget(self.page_info_label)
        
        main_layout.addWidget(status_bar)
    
    def _on_annotation_tool_changed(self, tool_name):
        """Handle annotation tool change."""
        if hasattr(self, 'pdf_view'):
            self.pdf_view.set_annotation_tool(tool_name)
            
            # Update status
            if tool_name == "select":
                self.status_label.setText("Ready (Selection mode)")
            elif tool_name == "highlight":
                self.status_label.setText("Ready (Highlight mode)")
            elif tool_name == "underline":
                self.status_label.setText("Ready (Underline mode)")
            elif tool_name == "strikeout":
                self.status_label.setText("Ready (Strikeout mode)")
    
    def _on_continuous_mode_changed(self, state):
        """Handle continuous mode toggle."""
        continuous_mode = state == Qt.CheckState.Checked.value
        if hasattr(self, 'pdf_view'):
            self.pdf_view.set_continuous_mode(continuous_mode)
    
    def _on_print(self):
        """Print the current document."""
        try:
            from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
            
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dialog = QPrintDialog(printer, self)
            
            if dialog.exec() == QPrintDialog.DialogCode.Accepted:
                # Print the document
                from PyQt6.QtGui import QPainter
                
                # Use PyMuPDF to render pages
                painter = QPainter(printer)
                
                # Get page range
                from_page = printer.fromPage() - 1 if printer.fromPage() > 0 else 0
                to_page = printer.toPage() - 1 if printer.toPage() > 0 else len(self.doc) - 1
                
                # Ensure valid page range
                from_page = max(0, min(from_page, len(self.doc) - 1))
                to_page = max(from_page, min(to_page, len(self.doc) - 1))
                
                # Show progress dialog
                progress = QProgressDialog("Printing document...", "Cancel", 0, to_page - from_page + 1, self)
                progress.setWindowTitle("Printing")
                progress.show()
                
                for i, page_num in enumerate(range(from_page, to_page + 1)):
                    # Check for cancel
                    if progress.wasCanceled():
                        break
                        
                    # Update progress
                    progress.setValue(i)
                    
                    # Start new page except for first page
                    if i > 0:
                        printer.newPage()
                    
                    # Render the page
                    page = self.doc[page_num]
                    zoom_matrix = fitz.Matrix(2.0, 2.0)  # Higher resolution for printing
                    pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
                    
                    # Convert to QImage and draw on printer
                    img_data = pix.samples
                    img = QImage(img_data, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
                    
                    # Scale to fit printer page
                    target_rect = printer.pageRect(QPrinter.Unit.DevicePixel)
                    source_rect = QRectF(0, 0, img.width(), img.height())
                    
                    # Maintain aspect ratio
                    scaled_rect = QRectF(source_rect)
                    scaled_rect.setSize(source_rect.size().scaled(target_rect.size(), Qt.AspectRatioMode.KeepAspectRatio))
                    
                    # Center on page
                    centered_rect = QRectF(
                        target_rect.left() + (target_rect.width() - scaled_rect.width()) / 2,
                        target_rect.top() + (target_rect.height() - scaled_rect.height()) / 2,
                        scaled_rect.width(),
                        scaled_rect.height()
                    )
                    
                    # Draw the image
                    painter.drawImage(centered_rect, img, source_rect)
                
                # Close progress dialog
                progress.close()
                
                # End painting
                painter.end()
                
                # Show success message
                QMessageBox.information(self, "Print Complete", "Document has been sent to the printer.")
        
        except Exception as e:
            logger.exception(f"Error printing document: {e}")
            QMessageBox.warning(self, "Print Error", f"An error occurred while printing: {str(e)}")
    
    def _on_save_current_page(self):
        """Save the current page as an image."""
        try:
            if not self.doc or self.current_page < 0 or self.current_page >= len(self.doc):
                return
                
            # Ask for save location and format
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Page As", 
                f"{os.path.splitext(self.document.title)[0]}_page{self.current_page+1}.png",
                "PNG Images (*.png);;JPEG Images (*.jpg);;All Files (*)"
            )
            
            if not file_path:
                return
                
            # Get the current page
            page = self.doc[self.current_page]
            
            # Render with high resolution
            zoom_matrix = fitz.Matrix(2.0, 2.0)  # Higher resolution
            pix = page.get_pixmap(matrix=zoom_matrix, alpha=False)
            
            # Convert to QImage and save
            img_data = pix.samples
            img = QImage(img_data, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
            
            # Save the image
            if img.save(file_path):
                QMessageBox.information(
                    self, "Save Successful", 
                    f"Page {self.current_page+1} saved as {file_path}"
                )
            else:
                QMessageBox.warning(
                    self, "Save Failed", 
                    f"Failed to save page as {file_path}"
                )
                
        except Exception as e:
            logger.exception(f"Error saving page as image: {e}")
            QMessageBox.warning(
                self, "Save Error", 
                f"An error occurred: {str(e)}"
            )
    
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
                    self.page_info_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")
                    
                    # Set the first page initially
                    self.pdf_view.set_page(self.doc, 0)
                
                logger.info(f"Loaded PDF with PyMuPDF: {file_path} with {self.total_pages} pages")
            except Exception as mupdf_error:
                # If PyMuPDF fails, try using QtPdf as a fallback
                logger.warning(f"PyMuPDF failed to load PDF: {mupdf_error}. Trying QPdfView fallback.")
                
                try:
                    from PyQt6.QtPdf import QPdfDocument
                    from PyQt6.QtPdfWidgets import QPdfView
                    
                    # Create a container for the QPdfView
                    container = QWidget()
                    container_layout = QVBoxLayout(container)
                    container_layout.setContentsMargins(0, 0, 0, 0)
                    
                    # Create QPdfView with the container as parent
                    pdf_qt_view = QPdfView(container)
                    
                    # Create PDF document
                    pdf_document = QPdfDocument()
                    
                    # Load the PDF file
                    pdf_document.load(file_path)
                    
                    # Set the document to the view
                    pdf_qt_view.setDocument(pdf_document)
                    
                    # Add to layout
                    container_layout.addWidget(pdf_qt_view)
                    
                    # Replace the PDF view with QPdfView
                    if hasattr(self, 'pdf_view'):
                        self.pdf_view.setParent(None)
                        self.pdf_view.deleteLater()
                    
                    # Add the container to the main layout
                    splitter = self.findChild(QSplitter)
                    if splitter and splitter.count() > 1:
                        splitter.widget(1).layout().addWidget(container)
                    
                    # Disable the UI elements that won't work with QPdfView
                    self.extract_action.setEnabled(False)
                    self.annotation_toolbar.setEnabled(False)
                    
                    # Add a notice about limited functionality
                    notice = QLabel("Limited functionality mode: Some features disabled")
                    notice.setStyleSheet("background-color: #FFF3CD; padding: 5px; border: 1px solid #FFEEBA;")
                    self.layout().insertWidget(0, notice)
                    
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
        
        # Enable/disable goto button
        self.goto_extract_button.setEnabled(len(self.extracts) > 0)
    
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
        
        # Enable/disable goto button
        self.goto_bookmark_button.setEnabled(len(self.bookmarks) > 0)
    
    @pyqtSlot()
    def _on_prev_page(self):
        """Go to previous page."""
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.page_spin.setValue(self.current_page + 1)
            self.pdf_view.set_page(self.doc, self.current_page)
            self.page_info_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")
    
    @pyqtSlot()
    def _on_next_page(self):
        """Go to next page."""
        if self.doc and self.current_page < len(self.doc) - 1:
            self.current_page += 1
            self.page_spin.setValue(self.current_page + 1)
            self.pdf_view.set_page(self.doc, self.current_page)
            self.page_info_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")
    
    @pyqtSlot(int)
    def _on_page_changed(self, page_number):
        """Handle page change from spin box."""
        if self.doc and 1 <= page_number <= len(self.doc):
            self.current_page = page_number - 1
            self.pdf_view.set_page(self.doc, self.current_page)
            self.page_info_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")
    
    @pyqtSlot(str)
    def _on_zoom_changed(self, zoom_text):
        """Handle zoom change."""
        try:
            zoom_factor = float(zoom_text.rstrip('%')) / 100.0
            self.pdf_view.set_zoom(zoom_factor)
        except ValueError:
            pass
    
    @pyqtSlot()
    def _on_zoom_in(self):
        """Zoom in."""
        current_zoom = self.pdf_view.zoom_factor
        self.pdf_view.set_zoom(min(3.0, current_zoom + 0.1))
        self._update_zoom_combo(self.pdf_view.zoom_factor)
    
    @pyqtSlot()
    def _on_zoom_out(self):
        """Zoom out."""
        current_zoom = self.pdf_view.zoom_factor
        self.pdf_view.set_zoom(max(0.5, current_zoom - 0.1))
        self._update_zoom_combo(self.pdf_view.zoom_factor)
    
    @pyqtSlot(str)
    def _on_selection_changed(self, selected_text):
        """Handle text selection changes."""
        self.create_extract_button.setEnabled(bool(selected_text))
        self.extract_action.setEnabled(bool(selected_text))
    
    @pyqtSlot()
    def _on_create_extract(self):
        """Create an extract from selected text."""
        selected_text = self.pdf_view.selected_text
        if not selected_text:
            logger.warning("No text selected for extract creation")
            QMessageBox.warning(self, "No Selection", "Please select text before creating an extract.")
            return

        # Log the selected text for debugging
        logger.info(f"Creating extract with text: '{selected_text[:50]}...'")

        try:
            # Highlight in PDF view
            self.pdf_view.add_highlight()

            # Get position info
            position = f"page:{self.current_page+1}"

            # Create extract
            extract = Extract(
                document_id=self.document.id,
                content=selected_text,
                context=f"Page {self.current_page+1}",
                position=position,
                priority=50,  # Default priority
                created_date=datetime.utcnow()
            )
            
            # Save extract to database
            self.db_session.add(extract)
            self.db_session.commit()

            # Reload extracts list
            self._load_extracts()

            # Emit signal
            self.extractCreated.emit(extract)

            # Show success message
            QMessageBox.information(
                self, "Extract Created",
                f"Extract successfully created from page {self.current_page+1}."
            )
            
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.critical(
                self, "Error",
                f"An error occurred while creating the extract: {str(e)}"
            )
   
    @pyqtSlot()
    def _on_add_bookmark(self):
        """Add a bookmark for the current page."""
        try:
            # Ask for bookmark text
            text, ok = QInputDialog.getText(
                self, "Add Bookmark", 
                "Enter bookmark description:",
                text=f"Bookmark on page {self.current_page+1}"
            )
            
            if not ok or not text:
                return
                
            # Make sure bookmarks attribute exists
            if not hasattr(self, 'bookmarks'):
                self.bookmarks = []
                
            # Add to bookmarks
            self.bookmarks.append({
                'page': self.current_page,
                'text': text
            })
            
            # Update display
            self._update_bookmarks_list()
            
            # Show success message
            QMessageBox.information(
                self, "Bookmark Added",
                f"Bookmark added for page {self.current_page+1}."
            )
            
            logger.debug(f"Added bookmark for page {self.current_page+1}: {text}")
        except Exception as e:
            logger.exception(f"Error adding bookmark: {e}")
            QMessageBox.warning(
                self, 
                "Bookmark Error", 
                f"Unable to add bookmark: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_goto_extract(self):
        """Go to the page containing a selected extract."""
        if not self.extracts:
            return
            
        # Build list of extracts for selection
        items = []
        for extract in self.extracts:
            # Try to extract page number from position info
            page_num = 0
            if hasattr(extract, 'position') and extract.position:
                try:
                    # Parse position info - format might be "page:N"
                    position_str = extract.position
                    if position_str.startswith('page:'):
                        page_num = int(position_str.split(':')[1]) - 1
                except Exception:
                    pass
            
            # Create item text
            text = f"Page {page_num+1}: {extract.content[:50]}..."
            items.append((text, page_num))
        
        # Show selection dialog
        item, ok = QInputDialog.getItem(
            self, "Go To Extract", 
            "Select an extract to navigate to:",
            [item[0] for item in items],
            0, False
        )
        
        if ok and item:
            # Find the selected extract
            for i, (text, page_num) in enumerate(items):
                if text == item:
                    # Navigate to the page
                    if 0 <= page_num < self.total_pages:
                        self.current_page = page_num
                        self.page_spin.setValue(self.current_page + 1)
                        self.pdf_view.set_page(self.doc, self.current_page)
                        self.page_info_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")
                    break
    
    @pyqtSlot()
    def _on_goto_bookmark(self):
        """Go to a selected bookmark."""
        if not self.bookmarks:
            return
            
        # Build list of bookmarks for selection
        items = []
        for bookmark in self.bookmarks:
            text = f"Page {bookmark['page']+1}: {bookmark['text']}"
            items.append((text, bookmark['page']))
        
        # Show selection dialog
        item, ok = QInputDialog.getItem(
            self, "Go To Bookmark", 
            "Select a bookmark to navigate to:",
            [item[0] for item in items],
            0, False
        )
        
        if ok and item:
            # Find the selected bookmark
            for i, (text, page_num) in enumerate(items):
                if text == item:
                    # Navigate to the page
                    if 0 <= page_num < self.total_pages:
                        self.current_page = page_num
                        self.page_spin.setValue(self.current_page + 1)
                        self.pdf_view.set_page(self.doc, self.current_page)
                        self.page_info_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")
                    break

    @pyqtSlot(int)
    def _on_page_requested(self, page_number):
        """Handle page change request from PDF view."""
        if self.doc and 0 <= page_number < len(self.doc):
            self.current_page = page_number
            self.page_spin.setValue(self.current_page + 1)
            self.pdf_view.set_page(self.doc, self.current_page)
            self.page_info_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")

    def closeEvent(self, event):
        """Handle widget close event to save position."""
        self._save_position()
        super().closeEvent(event)
