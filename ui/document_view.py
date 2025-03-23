import os
import logging
from typing import Optional, List, Dict
from datetime import datetime
import json
import time
import tempfile
from io import BytesIO
from pathlib import Path
import base64

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox, QApplication, QDialog,
    QTabWidget, QLineEdit, QSizePolicy, QCheckBox, QSlider, 
    QInputDialog, QComboBox, QStyle
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QUrl, QObject, QTimer, QPointF, QSize, QByteArray
from PyQt6.QtGui import QAction, QTextCursor, QColor, QTextCharFormat, QKeyEvent, QIntValidator, QIcon
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebChannel import QWebChannel
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

from core.knowledge_base.models import Document, Extract, WebHighlight
from core.content_extractor.extractor import ContentExtractor
from core.document_processor.handlers.epub_handler import EPUBHandler
from .document_extracts_view import DocumentExtractsView
from .load_epub_helper import setup_epub_webview
from .load_youtube_helper import setup_youtube_webview, extract_video_id_from_document
from .youtube_transcript_view import YouTubeTranscriptView
from core.spaced_repetition.incremental_reading import IncrementalReadingManager

logger = logging.getLogger(__name__)

class WebViewCallback(QObject):
    """Callback handler for JavaScript communication with WebView."""
    
    def __init__(self, document_view):
        """Initialize with document view reference."""
        super().__init__()
        self.document_view = document_view
    
    @pyqtSlot(str)
    def selectionChanged(self, text):
        """Handle text selection changes from WebView."""
        if self.document_view:
            self.document_view._handle_webview_selection(text)
    
    @pyqtSlot(str)
    def extractText(self, text):
        """Handle text extraction requests from WebView."""
        if self.document_view and text:
            self.document_view._handle_sm_extract_result(text)
    
    @pyqtSlot(str)
    def createCloze(self, text):
        """Handle cloze creation requests from WebView."""
        if self.document_view and text:
            self.document_view._handle_sm_cloze_result(text)
    
    @pyqtSlot()
    def skipItem(self):
        """Handle skip item requests from WebView."""
        if self.document_view:
            # This would connect to review scheduling
            pass

class VimKeyHandler:
    """Helper class for handling Vim-like key bindings."""
    
    def __init__(self, document_view):
        self.document_view = document_view
        self.vim_mode = True  # Default to Vim mode on
        self.command_mode = False  # Normal mode by default (not command mode)
        self.visual_mode = False  # Not in visual mode by default
        self.current_command = ""
        self.count_prefix = ""  # For number prefixes like 5j
        self.selection_start = None  # For visual mode selection
        self.selection_active = False
        
    def toggle_vim_mode(self):
        """Toggle Vim mode on/off."""
        self.vim_mode = not self.vim_mode
        if not self.vim_mode:
            self.command_mode = False
            self.visual_mode = False
            self.current_command = ""
        logger.debug(f"Vim mode {'enabled' if self.vim_mode else 'disabled'}")
        return self.vim_mode
        
    def handle_key_event(self, event):
        """Handle key events in Vim style."""
        if not self.vim_mode:
            return False
            
        # Get key information
        key = event.key()
        text = event.text()
        modifiers = event.modifiers()
        
        # Handle visual mode specially
        if self.visual_mode:
            return self._handle_visual_mode(key, text, modifiers)
            
        # Handle count prefix (numbers before commands)
        if not self.command_mode and text.isdigit() and self.count_prefix != "0":  # Don't start with 0
            self.count_prefix += text
            return True
            
        # Get count (default to 1 if no prefix)
        count = int(self.count_prefix) if self.count_prefix else 1
        
        # Handle command mode (after : key)
        if self.command_mode:
            if key == Qt.Key.Key_Escape:
                self.command_mode = False
                self.current_command = ""
                return True
            elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                self._execute_command(self.current_command)
                self.command_mode = False
                self.current_command = ""
                return True
            elif key == Qt.Key.Key_Backspace:
                self.current_command = self.current_command[:-1]
                return True
            else:
                self.current_command += text
                return True
        
        # Enter visual mode with v
        if key == Qt.Key.Key_V:
            self._enter_visual_mode()
            self.count_prefix = ""
            return True
                
        # Handle normal mode keys
        if key == Qt.Key.Key_J:  # j - move down
            self._scroll_down(count)
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_K:  # k - move up
            self._scroll_up(count)
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_G:  # g - go to top/bottom
            if modifiers & Qt.KeyboardModifier.ShiftModifier:  # G - go to bottom
                self._scroll_to_bottom()
            else:  # g - go to top
                self._scroll_to_top()
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_D:  # d - half page down
            if modifiers & Qt.KeyboardModifier.ControlModifier:  # Ctrl+d
                self._scroll_half_page_down()
                self.count_prefix = ""
                return True
                
        elif key == Qt.Key.Key_U:  # u - half page up
            if modifiers & Qt.KeyboardModifier.ControlModifier:  # Ctrl+u
                self._scroll_half_page_up()
                self.count_prefix = ""
                return True
                
        elif key == Qt.Key.Key_F:  # f - page down
            if modifiers & Qt.KeyboardModifier.ControlModifier:  # Ctrl+f
                self._scroll_page_down()
                self.count_prefix = ""
                return True
                
        elif key == Qt.Key.Key_B:  # b - page up
            if modifiers & Qt.KeyboardModifier.ControlModifier:  # Ctrl+b
                self._scroll_page_up()
                self.count_prefix = ""
                return True
                
        elif key == Qt.Key.Key_Slash:  # / - search
            # TODO: Implement search functionality
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_Colon:  # : - command mode
            self.command_mode = True
            self.current_command = ""
            self.count_prefix = ""
            return True
            
        elif key == Qt.Key.Key_Escape:  # ESC - clear state
            self.count_prefix = ""
            return True
            
        # If we've gotten this far and still have a count_prefix, it wasn't used,
        # so we should clear it
        self.count_prefix = ""
        return False
    
    def _handle_visual_mode(self, key, text, modifiers):
        """Handle key events while in visual mode."""
        # Exit visual mode with Escape
        if key == Qt.Key.Key_Escape:
            self._exit_visual_mode()
            return True
            
        # Extract text with 'e'
        if key == Qt.Key.Key_E:
            self._extract_selected_text()
            self._exit_visual_mode()
            return True
            
        # Flashcard with 'f'
        if key == Qt.Key.Key_F:
            self._create_flashcard()
            self._exit_visual_mode()
            return True
            
        # Cloze deletion with 'c'
        if key == Qt.Key.Key_C:
            self._create_cloze_deletion()
            self._exit_visual_mode()
            return True
            
        # Movement keys to extend selection
        if key == Qt.Key.Key_H:  # left
            self._extend_selection_left()
            return True
            
        if key == Qt.Key.Key_J:  # down
            self._extend_selection_down()
            return True
            
        if key == Qt.Key.Key_K:  # up
            self._extend_selection_up()
            return True
            
        if key == Qt.Key.Key_L:  # right
            self._extend_selection_right()
            return True
            
        if key == Qt.Key.Key_W:  # word forward
            self._extend_selection_word_forward()
            return True
            
        if key == Qt.Key.Key_B:  # word backward
            self._extend_selection_word_backward()
            return True
            
        return True  # Consume all keys in visual mode
    
    def _enter_visual_mode(self):
        """Enter visual mode for text selection."""
        self.visual_mode = True
        logger.debug("Entering visual mode")
        
        content_edit = self.document_view.content_edit
        
        # Setup based on content type
        if isinstance(content_edit, QTextEdit):
            # For text edit, ensure cursor is visible
            cursor = content_edit.textCursor()
            self.selection_start = cursor.position()
            content_edit.ensureCursorVisible()
            
            # Set a different cursor shape to indicate visual mode
            content_edit.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, set cursor style with JavaScript
            script = """
            document.body.style.cursor = 'text';
            
            // Create selection markers
            const marker = document.createElement('div');
            marker.id = 'vim-cursor-marker';
            marker.style.position = 'absolute';
            marker.style.width = '2px';
            marker.style.height = '1.2em';
            marker.style.backgroundColor = 'rgba(255, 0, 0, 0.7)';
            marker.style.zIndex = '9999';
            
            // Add to document
            document.body.appendChild(marker);
            
            // Position at beginning of first text node we can find
            const textNodes = [];
            function findTextNodes(node) {
                if (node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 0) {
                    textNodes.push(node);
                } else {
                    for (let i = 0; i < node.childNodes.length; i++) {
                        findTextNodes(node.childNodes[i]);
                    }
                }
            }
            
            findTextNodes(document.body);
            
            // If we found any text nodes, create a selection
            if (textNodes.length > 0) {
                const range = document.createRange();
                range.setStart(textNodes[0], 0);
                range.setEnd(textNodes[0], 0);
                
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                
                // Position marker at selection start
                const rect = range.getBoundingClientRect();
                marker.style.left = rect.left + 'px';
                marker.style.top = rect.top + 'px';
                
                // Store initial position in a way we can access later
                window.vimVisualModeStart = {
                    node: textNodes[0],
                    offset: 0
                };
            }
            """
            content_edit.page().runJavaScript(script)
        
        # Update the mode display
        self.document_view.vim_status_label.setText("Vim Mode: Visual")
        
    def _exit_visual_mode(self):
        """Exit visual mode."""
        self.visual_mode = False
        logger.debug("Exiting visual mode")
        
        content_edit = self.document_view.content_edit
        
        # Reset cursor/selection based on content type
        if isinstance(content_edit, QTextEdit):
            # Reset cursor shape
            content_edit.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Reset cursor and remove visual markers with JavaScript
            script = """
            document.body.style.cursor = 'auto';
            
            // Remove any selection marker
            const marker = document.getElementById('vim-cursor-marker');
            if (marker) {
                marker.parentNode.removeChild(marker);
            }
            
            // Clear selection
            window.getSelection().removeAllRanges();
            delete window.vimVisualModeStart;
            """
            content_edit.page().runJavaScript(script)
        
        # Update mode display
        self.document_view.vim_status_label.setText("Vim Mode: Normal")
    
    def _scroll_down(self, count=1):
        """Scroll down by count lines."""
        content_edit = self.document_view.content_edit
        
        # Handle different widget types
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Use line height as scroll unit
                line_height = content_edit.fontMetrics().height()
                scrollbar.setValue(scrollbar.value() + count * line_height)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to scroll
            script = f"window.scrollBy(0, {count * 30});"  # 30px per line
            content_edit.page().runJavaScript(script)
        
    def _scroll_up(self, count=1):
        """Scroll up by count lines."""
        content_edit = self.document_view.content_edit
        
        # Handle different widget types
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Use line height as scroll unit
                line_height = content_edit.fontMetrics().height()
                scrollbar.setValue(scrollbar.value() - count * line_height)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to scroll
            script = f"window.scrollBy(0, -{count * 30});"  # 30px per line
            content_edit.page().runJavaScript(script)
    
    def _scroll_to_top(self):
        """Scroll to the top of the document."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            # For text edit, move cursor to start and ensure visible
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            content_edit.setTextCursor(cursor)
            content_edit.ensureCursorVisible()
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to scroll to top
            script = "window.scrollTo(0, 0);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_to_bottom(self):
        """Scroll to the bottom of the document."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            # For text edit, move cursor to end and ensure visible
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            content_edit.setTextCursor(cursor)
            content_edit.ensureCursorVisible()
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to scroll to bottom
            script = "window.scrollTo(0, document.body.scrollHeight);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_half_page_down(self):
        """Scroll down half a page (Ctrl+d in Vim)."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Calculate half page height
                page_step = scrollbar.pageStep()
                scrollbar.setValue(scrollbar.value() + page_step // 2)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to get window height and scroll
            script = "window.scrollBy(0, window.innerHeight / 2);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_half_page_up(self):
        """Scroll up half a page (Ctrl+u in Vim)."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Calculate half page height
                page_step = scrollbar.pageStep()
                scrollbar.setValue(scrollbar.value() - page_step // 2)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to get window height and scroll
            script = "window.scrollBy(0, -window.innerHeight / 2);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_page_down(self):
        """Scroll down a full page (Ctrl+f in Vim)."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Use page step
                page_step = scrollbar.pageStep()
                scrollbar.setValue(scrollbar.value() + page_step)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to get window height and scroll
            script = "window.scrollBy(0, window.innerHeight);"
            content_edit.page().runJavaScript(script)
    
    def _scroll_page_up(self):
        """Scroll up a full page (Ctrl+b in Vim)."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            scrollbar = content_edit.verticalScrollBar()
            if scrollbar:
                # Use page step
                page_step = scrollbar.pageStep()
                scrollbar.setValue(scrollbar.value() - page_step)
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # For web view, use JavaScript to get window height and scroll
            script = "window.scrollBy(0, -window.innerHeight);"
            content_edit.page().runJavaScript(script)
    
    def _execute_command(self, command):
        """Execute a Vim-like command."""
        command = command.strip()
        
        if not command:
            return
            
        logger.debug(f"Executing Vim command: {command}")
        
        # Handle basic commands
        if command in ['q', 'quit']:
            # Close the document
            self.document_view.close()
        elif command.startswith('set '):
            # Handle settings
            setting = command[4:].strip()
            if setting == 'novim':
                self.toggle_vim_mode()
            elif setting == 'vim':
                self.vim_mode = True
        # Add more commands as needed
    
    def _extract_selected_text(self):
        """Extract the currently selected text."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            selected_text = content_edit.textCursor().selectedText()
            if selected_text:
                self.document_view.selected_text = selected_text
                self.document_view._on_create_extract()
                
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Use JavaScript to get selected text
            script = """
            window.getSelection().toString();
            """
            content_edit.page().runJavaScript(
                script,
                lambda text: self._handle_extract_from_webview(text)
            )
    
    def _handle_extract_from_webview(self, text):
        """Handle extract creation from web view selected text."""
        if text and text.strip():
            self.document_view.selected_text = text.strip()
            self.document_view._on_create_extract()
    
    def _create_flashcard(self):
        """Create a flashcard from selected text."""
        # This would require integration with a flashcard system
        # For now, we'll just extract the text
        self._extract_selected_text()
        
        # TODO: Add flashcard-specific handling when a flashcard system is available
        logger.debug("Flashcard creation requested - extracting text for now")
    
    def _create_cloze_deletion(self):
        """Create a cloze deletion from selected text."""
        # This would require integration with a flashcard/cloze system
        # For now, we'll just extract the text
        self._extract_selected_text()
        
        # TODO: Add cloze-specific handling when a cloze system is available
        logger.debug("Cloze deletion requested - extracting text for now")
    
    def _extend_selection_left(self):
        """Extend selection to the left."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            script = """
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                
                // Try to extend one character left
                try {
                    const startNode = range.startContainer;
                    const startOffset = range.startOffset;
                    
                    if (startOffset > 0) {
                        // Can move left within current node
                        range.setStart(startNode, startOffset - 1);
                    } else {
                        // Need to find previous text node
                        // This is simplified - would need more complex traversal for complete implementation
                    }
                    
                    // Update selection
                    selection.removeAllRanges();
                    selection.addRange(range);
                    
                    // Update marker
                    const marker = document.getElementById('vim-cursor-marker');
                    if (marker) {
                        const rect = range.getBoundingClientRect();
                        marker.style.left = rect.left + 'px';
                        marker.style.top = rect.top + 'px';
                    }
                } catch (e) {
                    console.error('Error extending selection left:', e);
                }
            }
            return window.getSelection().toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_right(self):
        """Extend selection to the right."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            script = """
            const selection = window.getSelection();
            if (selection.rangeCount > 0) {
                const range = selection.getRangeAt(0);
                
                // Try to extend one character right
                try {
                    const endNode = range.endContainer;
                    const endOffset = range.endOffset;
                    
                    if (endNode.nodeType === Node.TEXT_NODE && endOffset < endNode.textContent.length) {
                        // Can move right within current text node
                        range.setEnd(endNode, endOffset + 1);
                    } else {
                        // Need to find next text node (simplified)
                    }
                    
                    // Update selection
                    selection.removeAllRanges();
                    selection.addRange(range);
                } catch (e) {
                    console.error('Error extending selection right:', e);
                }
            }
            return window.getSelection().toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_up(self):
        """Extend selection upward."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Up, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # This is quite complex in a web page - we'll use a simplified approach
            script = """
            const selection = window.getSelection();
            if (selection.rangeCount === 0) return '';
            
            // Get current range
            const range = selection.getRangeAt(0);
            
            // Create a point slightly above the start of current selection
            const startRect = range.getBoundingClientRect();
            const x = startRect.left;
            const y = startRect.top - 20; // Move up by approximate line height
            
            // Use document.caretPositionFromPoint or document.elementFromPoint
            let newNode, newOffset;
            
            if (document.caretPositionFromPoint) {
                const pos = document.caretPositionFromPoint(x, y);
                if (pos) {
                    newNode = pos.offsetNode;
                    newOffset = pos.offset;
                }
            } else if (document.elementFromPoint) {
                // Fallback method - less accurate
                const element = document.elementFromPoint(x, y);
                if (element && element.firstChild) {
                    newNode = element.firstChild;
                    newOffset = 0;
                }
            }
            
            // If we found a node, update selection
            if (newNode) {
                try {
                    // Create new range from new point to current end
                    const newRange = document.createRange();
                    newRange.setStart(newNode, newOffset);
                    newRange.setEnd(range.endContainer, range.endOffset);
                    
                    // Apply new selection
                    selection.removeAllRanges();
                    selection.addRange(newRange);
                } catch (e) {
                    console.error('Error extending selection up:', e);
                }
            }
            
            return selection.toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_down(self):
        """Extend selection downward."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Similar approach to _extend_selection_up but in opposite direction
            script = """
            const selection = window.getSelection();
            if (selection.rangeCount === 0) return '';
            
            // Get current range
            const range = selection.getRangeAt(0);
            
            // Create a point slightly below the end of current selection
            const endRect = range.getBoundingClientRect();
            const x = endRect.right;
            const y = endRect.bottom + 20; // Move down by approximate line height
            
            // Use document.caretPositionFromPoint or document.elementFromPoint
            let newNode, newOffset;
            
            if (document.caretPositionFromPoint) {
                const pos = document.caretPositionFromPoint(x, y);
                if (pos) {
                    newNode = pos.offsetNode;
                    newOffset = pos.offset;
                }
            } else if (document.elementFromPoint) {
                // Fallback method - less accurate
                const element = document.elementFromPoint(x, y);
                if (element && element.firstChild) {
                    newNode = element.firstChild;
                    newOffset = 0;
                }
            }
            
            // If we found a node, update selection
            if (newNode) {
                try {
                    // Create new range from current start to new point
                    const newRange = document.createRange();
                    newRange.setStart(range.startContainer, range.startOffset);
                    newRange.setEnd(newNode, newOffset);
                    
                    // Apply new selection
                    selection.removeAllRanges();
                    selection.addRange(newRange);
                } catch (e) {
                    console.error('Error extending selection down:', e);
                }
            }
            
            return selection.toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_word_forward(self):
        """Extend selection to the next word."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.NextWord, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Simplified word selection - better implementations would use text node traversal
            script = """
            const selection = window.getSelection();
            if (!selection.rangeCount) return '';
            
            const range = selection.getRangeAt(0);
            const endNode = range.endContainer;
            
            if (endNode.nodeType === Node.TEXT_NODE) {
                const text = endNode.textContent;
                const endOffset = range.endOffset;
                
                // Find next word boundary
                let nextSpace = text.indexOf(' ', endOffset);
                if (nextSpace === -1) nextSpace = text.length;
                
                // Extend to word boundary
                range.setEnd(endNode, nextSpace + 1);
                
                // Update selection
                selection.removeAllRanges();
                selection.addRange(range);
            }
            
            return selection.toString();
            """
            content_edit.page().runJavaScript(script)
    
    def _extend_selection_word_backward(self):
        """Extend selection to the previous word."""
        content_edit = self.document_view.content_edit
        
        if isinstance(content_edit, QTextEdit):
            cursor = content_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.PreviousWord, QTextCursor.MoveMode.KeepAnchor)
            content_edit.setTextCursor(cursor)
            
        elif HAS_WEBENGINE and isinstance(content_edit, QWebEngineView):
            # Simplified word selection - better implementations would use text node traversal
            script = """
            const selection = window.getSelection();
            if (!selection.rangeCount) return '';
            
            const range = selection.getRangeAt(0);
            const startNode = range.startContainer;
            
            if (startNode.nodeType === Node.TEXT_NODE) {
                const text = startNode.textContent;
                const startOffset = range.startOffset;
                
                // Find previous word boundary
                const textBefore = text.substring(0, startOffset);
                let prevSpace = textBefore.lastIndexOf(' ');
                
                // If no space found, go to beginning of text
                if (prevSpace === -1) prevSpace = 0;
                else prevSpace += 1; // Move past the space
                
                // Extend selection
                range.setStart(startNode, prevSpace);
                
                // Update selection
                selection.removeAllRanges();
                selection.addRange(range);
            }
            
            return selection.toString();
            """
            content_edit.page().runJavaScript(script)

class DocumentView(QWidget):
    """UI component for viewing and processing documents."""
    
    extractCreated = pyqtSignal(int)  # extract_id
    
    def __init__(self, db_session, document_id=None):
        super().__init__()
        
        self.db_session = db_session
        self.document_id = document_id
        self.document = None
        self.selected_text = ""
        self.content_text = ""
        self.youtube_callback = None
        
        # View state tracking
        self.view_state = {
            "zoom_factor": 1.0,
            "position": None,
            "size": None,
            "scroll_position": 0
        }
        
        # Create the Vim key handler
        self.vim_handler = VimKeyHandler(self)
        
        # Create the UI
        self._create_ui()
        
        # Load document if provided
        if document_id:
            self.load_document(document_id)
    
    def _create_ui(self):
        """Create the UI components."""
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # Content splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Document content area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)  # Minimize spacing between elements
        
        # Content will be added dynamically based on document type
        
        splitter.addWidget(self.content_widget)
        
        # Extracts area
        self.extract_view = DocumentExtractsView(self.db_session)
        self.extract_view.extractSelected.connect(self._on_extract_selected)
        splitter.addWidget(self.extract_view)
        
        # Set initial sizes - give almost all space to the PDF content (95/5 split)
        splitter.setSizes([950, 50])
        
        # Make sure the split ratio is maintained when resizing
        splitter.setStretchFactor(0, 19)  # Content gets 19x the stretch of extracts
        splitter.setStretchFactor(1, 1)   # Extracts get 1x stretch factor
        
        layout.addWidget(splitter, 1)  # Add stretch factor of 1 to expand
        
        # Add Vim mode status bar - use minimal height
        self.vim_status_widget = QWidget()
        self.vim_status_widget.setMaximumHeight(20)  # Limit height
        vim_status_layout = QHBoxLayout(self.vim_status_widget)
        vim_status_layout.setContentsMargins(2, 1, 2, 1)  # Minimal margins
        
        self.vim_status_label = QLabel("Vim Mode: Normal")
        vim_status_layout.addWidget(self.vim_status_label)
        
        # Add vim command display
        self.vim_command_label = QLabel("")
        vim_status_layout.addWidget(self.vim_command_label)
        
        # Add visual mode indicator
        self.vim_visual_label = QLabel("")
        self.vim_visual_label.setStyleSheet("color: #c22;")  # Red text for visual mode
        vim_status_layout.addWidget(self.vim_visual_label)
        
        vim_status_layout.addStretch(1)  # Push everything to the left
        
        # Add keyboard shortcuts info
        self.vim_shortcuts_label = QLabel("v:visual e:extract f:flashcard c:cloze")
        self.vim_shortcuts_label.setStyleSheet("color: #666; font-size: 9pt;")
        vim_status_layout.addWidget(self.vim_shortcuts_label)
        
        layout.addWidget(self.vim_status_widget)
        self.vim_status_widget.setVisible(False)  # Hide by default
        
        self.setLayout(layout)
        
        # Initialize Vim key handler
        self.vim_key_handler = VimKeyHandler(self)
    
    def _clear_content_layout(self):
        """Clear the content layout by removing all widgets."""
        if hasattr(self, 'content_layout') and self.content_layout:
            # Remove each widget from the layout
            while self.content_layout.count():
                item = self.content_layout.takeAt(0)
                widget = item.widget()
                
                if widget:
                    widget.setParent(None)  # Remove parent relationship
                    widget.deleteLater()     # Schedule for deletion
    
    def _update_vim_status_visibility(self):
        """Update the visibility of the Vim status bar based on Vim mode state."""
        self.vim_status_widget.setVisible(self.vim_key_handler.vim_mode)
    
    def _toggle_vim_mode(self):
        """Toggle Vim mode on/off."""
        is_enabled = self.vim_key_handler.toggle_vim_mode()
        self.vim_toggle_action.setChecked(is_enabled)
        self._update_vim_status_visibility()
    
    def keyPressEvent(self, event):
        """Handle key press events for Vim-like navigation."""
        # Check if Vim handler wants to handle this key
        if self.vim_key_handler.handle_key_event(event):
            # Update command display if in command mode
            if self.vim_key_handler.command_mode:
                self.vim_status_label.setText("Vim Mode: Command")
                self.vim_command_label.setText(":" + self.vim_key_handler.current_command)
                self.vim_visual_label.setText("")
            elif self.vim_key_handler.visual_mode:
                self.vim_status_label.setText("Vim Mode: Visual")
                self.vim_command_label.setText("")
                self.vim_visual_label.setText("[Selection Mode]")
            else:
                self.vim_status_label.setText("Vim Mode: Normal")
                self.vim_visual_label.setText("")
                # Show count prefix if any
                if self.vim_key_handler.count_prefix:
                    self.vim_command_label.setText(self.vim_key_handler.count_prefix)
                else:
                    self.vim_command_label.setText("")
            
            # Event was handled
            return
        
        # If not handled by Vim mode, pass to parent
        super().keyPressEvent(event)
    
    def _create_webview_and_setup(self, html_content, base_url):
        """Create a QWebEngineView and set it up with the content."""
        if not HAS_WEBENGINE:
            logger.warning("QWebEngineView not available, falling back to QTextEdit")
            editor = QTextEdit()
            editor.setReadOnly(True)
            editor.setHtml(html_content)
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            return editor
        
        # Create WebEngine view for HTML content
        webview = QWebEngineView()
        
        # Set size policy to expand
        webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Configure settings to allow all JavaScript functionality
        settings = webview.settings()
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(settings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(settings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(settings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, True)
        
        # Create a channel for JavaScript communication
        channel = QWebChannel(webview.page())
        
        # Create callback handler
        callback_handler = WebViewCallback(self)
        channel.registerObject("callbackHandler", callback_handler)
        
        # Set the channel to the page
        webview.page().setWebChannel(channel)
        
        # Check if we need to inject JavaScript libraries
        injected_html = self._inject_javascript_libraries(html_content)
        
        # Load content with proper base URL for resources
        if base_url:
            webview.setHtml(injected_html, base_url)
        else:
            webview.setHtml(injected_html)
        
        # Inject JavaScript to capture selections - using a cleaner approach
        selection_js = """
        // Wait for document to be fully loaded
        document.addEventListener('DOMContentLoaded', function() {
            // Add selection change listener
            document.addEventListener('selectionchange', function() {
                const selection = window.getSelection();
                const text = selection.toString();
                // Only send non-empty selections
                if (text && text.trim().length > 0) {
                    // Check if callback handler is available
                    if (typeof window.callbackHandler !== 'undefined') {
                        window.callbackHandler.selectionChanged(text);
                    } else {
                        console.error('Callback handler not available');
                    }
                }
            });

            // Track scroll position changes
            document.addEventListener('scroll', function() {
                // Throttle scroll events to reduce overhead
                if (window.scrollTrackTimeout) {
                    clearTimeout(window.scrollTrackTimeout);
                }
                window.scrollTrackTimeout = setTimeout(function() {
                    const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
                    if (typeof window.callbackHandler !== 'undefined') {
                        // Store position in a window variable so we can access it later
                        window.lastScrollPosition = scrollPosition;
                    }
                }, 200); // 200ms throttle
            });
            
            // Initialize any custom libraries
            if (typeof initializeCustomLibraries === 'function') {
                try {
                    initializeCustomLibraries();
                    console.log('Custom libraries initialized');
                } catch (e) {
                    console.error('Error initializing custom libraries:', e);
                }
            }
        });
        """
        
        # Simple direct selection capture script as fallback
        simple_selection_js = """
        document.onselectionchange = function() {
            var selection = window.getSelection();
            var text = selection.toString();
            if (text && text.trim().length > 0) {
                window.text_selection = text; // Store in a global variable
            }
        };
        """
        
        # Inject the simple selection script immediately
        webview.page().runJavaScript(simple_selection_js)
        
        # Inject the main script after the page has loaded
        webview.loadFinished.connect(lambda ok: webview.page().runJavaScript(selection_js))
        
        # Add a method to manually get the current selection
        def check_selection():
            webview.page().runJavaScript(
                "window.getSelection().toString() || window.text_selection || '';",
                self._handle_webview_selection
            )
        
        # Store the method to check selection
        webview.check_selection = check_selection
        
        # Connect mouse release to check selection
        webview.mouseReleaseEvent = lambda event: (
            super(QWebEngineView, webview).mouseReleaseEvent(event),
            check_selection()
        )
        
        # Connect context menu request to check selection before showing menu
        webview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # Store the original handler
        original_handler = self._on_content_menu
        
        # Create a wrapper that first checks selection
        def context_menu_wrapper(pos):
            check_selection()
            # Call the original handler after a small delay
            QApplication.processEvents()
            original_handler(pos)
        
        webview.customContextMenuRequested.connect(context_menu_wrapper)
        
        return webview
    
    def _inject_javascript_libraries(self, html_content):
        """Inject common JavaScript libraries into HTML content based on content needs."""
        
        # Check if the document already has a head tag
        has_head = "<head>" in html_content
        has_body = "<body>" in html_content
        
        # Library CDN URLs
        libraries = {
            'markdown': "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
            'mermaid': "https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js",
            'plotly': "https://cdn.plot.ly/plotly-latest.min.js",
            'katex': "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js",
            'katex-css': "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css",
            'katex-autorender': "https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js",
            'three': "https://cdn.jsdelivr.net/npm/three@0.157.0/build/three.min.js"
        }
        
        # Determine which libraries to inject based on content
        to_inject = []
        
        # Check for library markers in content
        if "```mermaid" in html_content or "mermaid" in html_content:
            to_inject.append('mermaid')
        
        if "```math" in html_content or "\\(" in html_content or "\\[" in html_content or "$" in html_content or "math" in html_content.lower():
            to_inject.append('katex')
            to_inject.append('katex-css')
            to_inject.append('katex-autorender')
        
        if "```plotly" in html_content or "Plotly" in html_content:
            to_inject.append('plotly')
        
        if "```markdown" in html_content or "marked" in html_content or "markdown" in html_content.lower():
            to_inject.append('markdown')
        
        if "three.js" in html_content or "THREE." in html_content:
            to_inject.append('three')
        
        # Return original content if no libraries needed or if we can't find insertion points
        if not to_inject or (not has_head and not has_body):
            return html_content
        
        # Build script tags
        scripts = ""
        styles = ""
        
        for lib in to_inject:
            if lib.endswith('-css'):
                styles += f'<link rel="stylesheet" href="{libraries[lib]}">\n'
            else:
                scripts += f'<script src="{libraries[lib]}"></script>\n'
        
        # Add initialization script
        init_script = """
<script>
function initializeCustomLibraries() {
    // Initialize mermaid if available
    if (typeof mermaid !== 'undefined') {
        try {
            mermaid.initialize({
                startOnLoad: true,
                theme: 'neutral'
            });
        } catch (e) {
            console.error('Mermaid init error:', e);
        }
    }
    
    // Initialize KaTeX if available
    if (typeof katex !== 'undefined') {
        console.log('KaTeX detected, initializing...');
        
        // First approach: Find specific elements with class names
        document.querySelectorAll('.math, .katex').forEach(element => {
            try {
                // Get the raw text and trim whitespace
                let texContent = element.textContent.trim();
                console.log('Processing KaTeX element:', texContent.substring(0, 30) + '...');
                
                // Create a new element to render into (to avoid modifying the original)
                let renderElement = document.createElement('div');
                renderElement.className = 'katex-output';
                element.innerHTML = ''; // Clear the original content
                element.appendChild(renderElement);
                
                // Render the KaTeX
                katex.render(texContent, renderElement, {
                    throwOnError: false,
                    displayMode: element.classList.contains('display')
                });
            } catch (e) {
                console.error('KaTeX rendering error:', e);
                element.innerHTML = '<span style="color:red">KaTeX Error: ' + e.message + '</span><br>' + element.textContent;
            }
        });
        
        // Render inline math
        document.querySelectorAll('.math-inline').forEach(element => {
            try {
                let texContent = element.textContent.trim();
                katex.render(texContent, element, {
                    throwOnError: false,
                    displayMode: false
                });
            } catch (e) {
                console.error('KaTeX inline error:', e);
                element.innerHTML = '<span style="color:red">Error</span>';
            }
        });
        
        // Second approach: Use the auto-render extension if available
        if (typeof renderMathInElement !== 'undefined') {
            console.log('Using KaTeX auto-render extension');
            try {
                // Automatically render math in the entire document
                renderMathInElement(document.body, {
                    delimiters: [
                        {left: "$$", right: "$$", display: true},
                        {left: "$", right: "$", display: false},
                        {left: "\\(", right: "\\)", display: false},
                        {left: "\\[", right: "\\]", display: true}
                    ],
                    throwOnError: false
                });
            } catch (e) {
                console.error('KaTeX auto-render error:', e);
            }
        }
    }
    
    // Initialize markdown if available
    if (typeof marked !== 'undefined') {
        console.log('Marked.js detected, initializing...');
        
        // Set up marked options for better rendering
        marked.setOptions({
            gfm: true,          // Enable GitHub flavored markdown
            breaks: true,       // Convert line breaks to <br>
            smartLists: true,   // Use smart list behavior
            smartypants: true,  // Use smart punctuation
            xhtml: true         // Return XHTML compliant output
        });
        
        document.querySelectorAll('.markdown').forEach(element => {
            try {
                // Get the raw text
                let mdContent = element.textContent.trim();
                console.log('Processing Markdown element:', mdContent.substring(0, 30) + '...');
                
                // Parse markdown
                let htmlContent = marked.parse(mdContent);
                
                // Create a wrapper to maintain any styling
                let wrapper = document.createElement('div');
                wrapper.className = 'markdown-output';
                wrapper.innerHTML = htmlContent;
                
                // Replace content
                element.innerHTML = '';
                element.appendChild(wrapper);
            } catch (e) {
                console.error('Markdown error:', e);
                element.innerHTML = '<div class="error">Markdown rendering error: ' + e.message + '</div>';
            }
        });
    }
    
    console.log('Custom libraries initialization complete');
}

// Execute after DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, initializing custom libraries');
    setTimeout(initializeCustomLibraries, 100);
});

// Add a button to manually trigger initialization if automatic doesn't work
window.addEventListener('load', function() {
    // Check if any library-specific elements exist but haven't been processed
    let needsInit = (
        (document.querySelector('.markdown') && !document.querySelector('.markdown-output')) ||
        (document.querySelector('.math, .katex') && !document.querySelector('.katex-output'))
    );
    
    if (needsInit) {
        console.log('Library elements found that need initialization');
        
        // Create a button to manually trigger initialization
        let btn = document.createElement('button');
        btn.textContent = 'Initialize Custom Content';
        btn.style.position = 'fixed';
        btn.style.bottom = '10px';
        btn.style.right = '10px';
        btn.style.zIndex = '9999';
        btn.style.padding = '8px 16px';
        btn.style.backgroundColor = '#0066cc';
        btn.style.color = 'white';
        btn.style.border = 'none';
        btn.style.borderRadius = '4px';
        btn.style.cursor = 'pointer';
        
        btn.onclick = function() {
            initializeCustomLibraries();
            btn.textContent = 'Initialization Complete';
            setTimeout(function() { 
                btn.style.display = 'none'; 
            }, 2000);
        };
        
        document.body.appendChild(btn);
        
        // Try one more time automatically
        setTimeout(initializeCustomLibraries, 1000);
    }
});
</script>
"""
        
        # Inject into HTML
        if has_head:
            # Insert before the closing head tag
            html_content = html_content.replace("</head>", styles + scripts + init_script + "</head>")
        elif has_body:
            # Insert after the opening body tag
            html_content = html_content.replace("<body>", "<body>\n" + styles + scripts + init_script)
        else:
            # Wrap the entire content
            html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Document</title>
    {styles}
    {scripts}
    {init_script}
</head>
<body>
    {html_content}
</body>
</html>
"""
        
        return html_content
    
    def keep_alive(self, obj):
        """Keep a reference to an object to prevent garbage collection."""
        if not hasattr(self, '_kept_references'):
            self._kept_references = []
        self._kept_references.append(obj)
        
    def load_document(self, document_id):
        """Load a document for viewing.
        
        Args:
            document_id (int): ID of the document to load.
        """
        try:
            # Keep any existing references alive
            if hasattr(self, 'webview'):
                self.keep_alive(self.webview)
            if hasattr(self, 'youtube_callback'):
                self.keep_alive(self.youtube_callback)
                
            # Clear the document area
            self._clear_content_layout()
            
            # Get the document
            self.document_id = document_id
            self.document = self.db_session.query(Document).filter_by(id=document_id).first()
            
            if not self.document:
                raise ValueError(f"Document not found: {document_id}")
            
            # Update extracts view
            if hasattr(self, 'extract_view') and self.extract_view:
                self.extract_view.load_extracts_for_document(document_id)
            
            # Load the document content based on its type
            doc_type = self.document.content_type.lower() if hasattr(self.document, 'content_type') and self.document.content_type else "text"
            
            logger.debug(f"Loading document: {self.document.title} (Type: {doc_type})")
            
            # Handle different document types
            if doc_type == "youtube":
                self._load_youtube()
            elif doc_type == "epub":
                self._load_epub(self.db_session, self.document)
            elif doc_type == "pdf":
                self._load_pdf()
            elif doc_type == "html" or doc_type == "htm":
                self._load_html()
            elif doc_type == "txt":
                self._load_text()
            else:
                # Default to text view
                self._load_text()
            
            # Set window title to document title
            if hasattr(self, 'setWindowTitle') and callable(self.setWindowTitle):
                self.setWindowTitle(self.document.title)
                
            return True
        except Exception as e:
            logger.exception(f"Error loading document {document_id}: {e}")
            
            # Show error in view
            error_widget = QLabel(f"Error loading document: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            
            self._clear_content_layout()
            if hasattr(self, 'content_layout'):
                self.content_layout.addWidget(error_widget)
                
            return False
    
    def _load_pdf(self):
        """Load and display a PDF document."""
        try:
            file_path = self.document.file_path
            
            # Check if file exists
            if not os.path.isfile(file_path):
                logger.error(f"PDF file not found: {file_path}")
                
                # Try alternative file path if in temporary directory
                if '/tmp/' in file_path:
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
            
            # First try using PyMuPDF for advanced features
            try:
                import fitz  # PyMuPDF
                
                # Custom PDF viewer using PyMuPDF
                from ui.pdf_view import PDFViewWidget
                
                # Create the PDF view widget
                pdf_widget = PDFViewWidget(self.document, self.db_session)
                
                # Connect extract created signal if available
                if hasattr(self, 'extractCreated') and hasattr(pdf_widget, 'extractCreated'):
                    pdf_widget.extractCreated.connect(self.extractCreated.emit)
                
                # Add to layout
                self.content_layout.addWidget(pdf_widget)
                
                # Store content edit for later use
                self.content_edit = pdf_widget
                
                logger.info(f"Loaded PDF with PyMuPDF: {file_path}")
                return
                
            except (ImportError, Exception) as e:
                logger.warning(f"Could not use PyMuPDF for PDF: {str(e)}. Falling back to QPdfView.")
                # Fall back to QPdfView
                pass
                
            # Fallback: Use QPdfView from Qt
            from PyQt6.QtPdf import QPdfDocument
            from PyQt6.QtPdfWidgets import QPdfView
            
            # Create PDF view
            pdf_view = QPdfView()
            
            # Create PDF document
            pdf_document = QPdfDocument()
            
            # Load the PDF file
            pdf_document.load(file_path)
            
            # Set the document to the view
            pdf_view.setDocument(pdf_document)
            
            # Add to layout
            self.content_layout.addWidget(pdf_view)
            
            # Store content edit for later use (position tracking)
            self.content_edit = pdf_view
            
            # Extract text content for context
            # This would require a PDF text extraction library
            self.content_text = "PDF content"
            
            # Restore reading position if available
            self._restore_position()
            
            logger.info(f"Loaded PDF with QPdfView: {file_path}")
            
        except ImportError:
            logger.error("PDF viewing requires PyQt6.QtPdf and PyQt6.QtPdfWidgets")
            label = QLabel("PDF viewing requires additional modules that are not installed.")
            self.content_layout.addWidget(label)
        except Exception as e:
            logger.exception(f"Error loading PDF: {e}")
            label = QLabel(f"Error loading PDF: {str(e)}")
            self.content_layout.addWidget(label)

    def _load_youtube(self):
        """Load and display a YouTube video document."""
        try:
            if not HAS_WEBENGINE:
                raise Exception("WebEngine not available. YouTube viewing requires PyQt6 WebEngine.")
            
            # Extract video ID from document content or URL
            video_id = extract_video_id_from_document(self.document)
            
            if not video_id:
                raise ValueError("Could not extract YouTube video ID from document")
            
            # Create a QWebEngineView for embedding YouTube
            web_view = QWebEngineView()
            web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            
            # Create a callback handler for communication with the player
            self.youtube_callback = WebViewCallback(self)
            
            # Configure the YouTube player with our load_youtube_helper
            # Get the target position from the document if available
            target_position = getattr(self.document, 'position', 0)
            
            # Use the proper setup_youtube_webview function with all required parameters
            success, callback = setup_youtube_webview(
                web_view, 
                self.document, 
                video_id, 
                target_position=target_position,
                db_session=self.db_session
            )
            
            if not success:
                raise ValueError(f"Failed to set up YouTube player for video ID: {video_id}")
                
            # Store the enhanced callback
            self.youtube_enhanced_callback = callback
            
            # Add to layout
            self.content_layout.addWidget(web_view)
            
            # Store references
            self.web_view = web_view
            self.content_edit = web_view
            
            # Add transcript view if available
            try:
                # Create a transcript view widget
                transcript_view = YouTubeTranscriptView(video_id, self.db_session)
                transcript_view.setMaximumHeight(200)  # Limit height
                
                # Connect transcript navigation signals if available
                if hasattr(transcript_view, 'seekToTime'):
                    transcript_view.seekToTime.connect(
                        lambda time_sec: web_view.page().runJavaScript(
                            f"if(typeof player !== 'undefined' && player) {{ player.seekTo({time_sec}, true); }}"
                        )
                    )
                
                # Add to layout below the video
                self.content_layout.addWidget(transcript_view)
                
                # Store reference
                self.transcript_view = transcript_view
                
            except Exception as e:
                logger.warning(f"Could not load YouTube transcript: {e}")
                # Continue without transcript
            
            logger.info(f"Loaded YouTube video: {video_id}")
            
        except Exception as e:
            logger.exception(f"Error loading YouTube video: {e}")
            error_widget = QLabel(f"Error loading YouTube video: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_widget)

    def _load_epub(self, db_session, document):
        """
        Load document in EPUB format.
        
        Args:
            db_session: SQLAlchemy session
            document: Document object
            
        Returns:
            bool: True if document was loaded successfully
        """
        try:
            if not HAS_WEBENGINE:
                raise Exception("Web engine not available.")
            
            # Create the web view
            content_edit = QWebEngineView()
            
            # Load the EPUB into the handler
            try:
                epub_handler = EPUBHandler()
                # Load the file data and prepare it for the webview
                content_results = epub_handler.extract_content(document.file_path)
                html_content = content_results['html']
                
                # Check if we can detect any JS libraries in the HTML content
                # For better display with certain EPUB formats
                has_jquery = "jquery" in html_content.lower()
                
                # Apply jQuery from resources if not already in the HTML
                if not has_jquery:
                    logger.debug("EPUB does not contain jQuery, will inject if needed")
                    # Handled via injectScriptTag in later methods
                
                # Set the EPUB content to the view
                content_edit.setHtml(html_content, QUrl.fromLocalFile(document.file_path))
                
                # Set up position tracking
                from ui.load_epub_helper import setup_epub_webview
                from core.utils.theme_manager import ThemeManager
                
                # Get theme manager from MainWindow or create a new instance
                app = QApplication.instance()
                main_window = None
                for widget in app.topLevelWidgets():
                    if widget.__class__.__name__ == "MainWindow":
                        main_window = widget
                        break
                
                theme_manager = None
                if main_window and hasattr(main_window, 'theme_manager'):
                    theme_manager = main_window.theme_manager
                else:
                    # Create a new instance if not available
                    from core.utils.settings_manager import SettingsManager
                    settings_manager = SettingsManager()
                    theme_manager = ThemeManager(settings_manager)
                
                # Add SuperMemo SM-18 style incremental reading capabilities
                self._add_supermemo_features(content_edit)
                
                # Set up the EPUB view with theme
                setup_epub_webview(document, content_edit, db_session, restore_position=True, theme_manager=theme_manager)
                
                # Add it to our layout
                self.content_layout.addWidget(content_edit)
                
                # Store content for later use
                self.content_edit = content_edit
                self.content_text = content_results['text']
                
                return True
                
            except Exception as e:
                logger.exception(f"Error loading EPUB content: {e}")
                error_widget = QLabel(f"Error loading EPUB: {str(e)}")
                error_widget.setWordWrap(True)
                error_widget.setStyleSheet("color: red; padding: 20px;")
                self.content_layout.addWidget(error_widget)
                return False
                
        except Exception as e:
            logger.exception(f"Error setting up EPUB viewer: {e}")
            error_widget = QLabel(f"Error setting up EPUB viewer: {str(e)}")
            error_widget.setWordWrap(True)
            error_widget.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_widget)
            return False
    
    def _load_text(self):
        """Load and display a text document."""
        try:
            # Create text edit
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            
            # Set size policy to expand
            text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            
            # Check if file exists
            if not os.path.exists(self.document.file_path):
                logger.error(f"Text file does not exist: {self.document.file_path}")
                error_message = f"File not found: {os.path.basename(self.document.file_path)}\n\nThis may happen if the file was a temporary web page that has been removed."
                text_edit.setPlainText(error_message)
                self.content_layout.addWidget(text_edit, 1)
                self.content_edit = text_edit
                self.content_text = error_message
                return
            
            # Read file content
            with open(self.document.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Set content
            text_edit.setPlainText(content)
            
            # Add to layout - use stretch factor to expand
            self.content_layout.addWidget(text_edit, 1)
            
            # Store for later use
            self.content_edit = text_edit
            self.content_text = content
            
            # Restore position
            self._restore_position()
            
        except Exception as e:
            logger.exception(f"Error loading text document: {e}")
            label = QLabel(f"Error loading text document: {str(e)}")
            self.content_layout.addWidget(label)
    
    def _load_html(self):
        """Load and display an HTML document."""
        try:
            # Check if file exists
            if not os.path.exists(self.document.file_path):
                logger.error(f"HTML file does not exist: {self.document.file_path}")
                error_message = f"File not found: {os.path.basename(self.document.file_path)}"
                
                # Display error in a QLabel
                error_label = QLabel(error_message)
                error_label.setWordWrap(True)
                error_label.setStyleSheet("color: red; padding: 20px;")
                self.content_layout.addWidget(error_label)
                
                return
            
            # Read HTML content
            with open(self.document.file_path, 'r', encoding='utf-8', errors='replace') as f:
                html_content = f.read()
            
            # Get base URL for resources (images, stylesheets)
            base_url = QUrl.fromLocalFile(os.path.dirname(self.document.file_path) + os.sep)
            
            # Create WebView with the HTML content
            web_view = self._create_webview_and_setup(html_content, base_url)
            
            # Add to layout
            self.content_layout.addWidget(web_view)
            
            # Store references for later use
            self.web_view = web_view
            self.content_edit = web_view
            self.content_text = html_content
            
            # Add SuperMemo-style incremental reading capabilities
            self._add_supermemo_features(web_view)
            
            # Restore previous reading position if available
            self._restore_position()
            
            logger.info(f"Loaded HTML document: {self.document.file_path}")
            
        except Exception as e:
            logger.exception(f"Error loading HTML document: {e}")
            error_label = QLabel(f"Error loading HTML document: {str(e)}")
            error_label.setWordWrap(True)
            error_label.setStyleSheet("color: red; padding: 20px;")
            self.content_layout.addWidget(error_label)

    def summarize_current_content(self):
        """Summarize the current document content using AI."""
        try:
            from core.document_processor.summarizer import DocumentSummarizer
            from core.utils.settings_manager import SettingsManager
            import tempfile
            import os
            
            # Get the document content
            document_id = getattr(self, 'document_id', None)
            
            if not document_id:
                logger.warning("No document loaded to summarize")
                QMessageBox.warning(
                    self, "Summarization Error", 
                    "Please load a document before trying to summarize content."
                )
                return
                
            # Create summarizer
            settings_manager = SettingsManager()
            summarizer = DocumentSummarizer(self.db_session, settings_manager)
            
            # For web content, extract directly from the web view if available
            if hasattr(self, 'web_view') and self.web_view:
                # Check if it's a web document from URL
                document = self.db_session.query(Document).get(document_id)
                if document and document.content_type == 'web':
                    # Get content from the webview
                    self.web_view.page().toHtml(self._on_html_extracted_for_summary)
                    return
                    
                # Alternatively, get the content as text from the webview
                self.web_view.page().toPlainText(self._on_text_extracted_for_summary)
                return
                
            # For non-web documents, use the existing summarize_document method
            result = summarizer.summarize_document(document_id)
            
            if result and result.get('success', False):
                summary = result.get('summary', 'No summary generated')
                
                # Show the summary
                self._show_summary_dialog(summary)
                
            else:
                error = result.get('error', 'Unknown error')
                QMessageBox.warning(
                    self, "Summarization Failed", 
                    f"Failed to summarize document: {error}"
                )
                
        except Exception as e:
            logger.exception(f"Error summarizing content: {e}")
            QMessageBox.warning(
                self, "Summarization Error", 
                f"An error occurred while trying to summarize the content: {str(e)}"
            )

    @pyqtSlot(int)
    def _on_extract_selected(self, extract_id):
        """Handle extract selection from extract view."""
        self.extractCreated.emit(extract_id)
                
    def _on_html_extracted_for_summary(self, html_content):
        """Process extracted HTML content for summarization."""
        try:
            from core.document_processor.summarizer import DocumentSummarizer
            from core.utils.settings_manager import SettingsManager
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(html_content, 'lxml')
            text_content = soup.get_text(separator='\n')
            
            # Get document title if available
            document = self.db_session.query(Document).get(self.document_id)
            title = document.title if document else ""
            
            # Create summarizer
            settings_manager = SettingsManager()
            summarizer = DocumentSummarizer(self.db_session, settings_manager)
            
            # Use the new web-specific summarization method
            result = summarizer.summarize_web_content(text_content, title)
            
            if result and result.get('success', False):
                summary = result.get('summary', 'No summary generated')
                
                # Show the summary
                self._show_summary_dialog(summary)
                
            else:
                error = result.get('error', 'Unknown error')
                QMessageBox.warning(
                    self, "Summarization Failed", 
                    f"Failed to summarize web content: {error}"
                )
                
        except Exception as e:
            logger.exception(f"Error summarizing HTML content: {e}")
            QMessageBox.warning(
                self, "Summarization Error", 
                f"An error occurred while summarizing HTML content: {str(e)}"
            )
            
    def _on_text_extracted_for_summary(self, text_content):
        """Process extracted text content for summarization."""
        try:
            from core.document_processor.summarizer import DocumentSummarizer
            from core.utils.settings_manager import SettingsManager
            
            # Get document title if available
            document = self.db_session.query(Document).get(self.document_id)
            title = document.title if document else ""
            
            # Create summarizer
            settings_manager = SettingsManager()
            summarizer = DocumentSummarizer(self.db_session, settings_manager)
            
            # Use the new web-specific summarization method
            result = summarizer.summarize_web_content(text_content, title)
            
            if result and result.get('success', False):
                summary = result.get('summary', 'No summary generated')
                
                # Show the summary
                self._show_summary_dialog(summary)
                
            else:
                error = result.get('error', 'Unknown error')
                QMessageBox.warning(
                    self, "Summarization Failed", 
                    f"Failed to summarize content: {error}"
                )
                
        except Exception as e:
            logger.exception(f"Error summarizing text content: {e}")
            QMessageBox.warning(
                self, "Summarization Error", 
                f"An error occurred while summarizing text content: {str(e)}"
            )
            
    def _show_summary_dialog(self, summary):
        """Show a dialog with the document summary."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Document Summary")
        dialog.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        # Summary text edit
        summary_text = QTextEdit()
        summary_text.setReadOnly(True)
        summary_text.setPlainText(summary)
        layout.addWidget(summary_text)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Save)
        button_box.accepted.connect(dialog.accept)
        
        # Connect save button
        save_button = button_box.button(QDialogButtonBox.StandardButton.Save)
        save_button.clicked.connect(lambda: self._save_summary(summary))
        
        layout.addWidget(button_box)
        
        dialog.exec()
        
    def _save_summary(self, summary):
        """Save the summary to a file."""
        from PyQt6.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Summary", "", "Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(summary)
                    
                QMessageBox.information(
                    self, "Summary Saved", 
                    f"Summary saved to {file_path}"
                )
                
            except Exception as e:
                logger.exception(f"Error saving summary: {e}")
                QMessageBox.warning(
                    self, "Save Error", 
                    f"An error occurred while saving the summary: {str(e)}"
                )

    def _on_previous(self):
        """Navigate to the previous page in the history."""
        if hasattr(self, 'web_view') and self.web_view:
            self.web_view.back()
        else:
            logger.debug("Previous action called but no webview available")
            
    def _on_next(self):
        """Navigate to the next page in the history."""
        if hasattr(self, 'web_view') and self.web_view:
            self.web_view.forward()
        else:
            logger.debug("Next action called but no webview available")

    def _create_toolbar(self):
        """Create the document viewer toolbar with actions."""
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        
        # Create actions
        self.prev_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward), "Previous", self)
        self.prev_action.triggered.connect(self._on_previous)
        toolbar.addAction(self.prev_action)
        
        self.next_action = QAction(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward), "Next", self)
        self.next_action.triggered.connect(self._on_next)
        toolbar.addAction(self.next_action)
        
        toolbar.addSeparator()
        
        # Add highlight action
        self.highlight_action = QAction(QIcon.fromTheme("edit-select-all"), "Highlight", self)
        self.highlight_action.triggered.connect(self._on_highlight)
        toolbar.addAction(self.highlight_action)
        
        # Add extract action
        self.extract_action = QAction(QIcon.fromTheme("edit-copy"), "Extract", self)
        self.extract_action.triggered.connect(self._on_extract)
        toolbar.addAction(self.extract_action)
        
        toolbar.addSeparator()
        
        # Add incremental reading actions
        self.add_to_ir_action = QAction(QIcon.fromTheme("bookmark-new"), "Add to Reading Queue", self)
        self.add_to_ir_action.triggered.connect(self._on_add_to_incremental_reading)
        toolbar.addAction(self.add_to_ir_action)
        
        self.mark_progress_action = QAction(QIcon.fromTheme("document-save"), "Mark Reading Progress", self)
        self.mark_progress_action.triggered.connect(self._on_mark_reading_progress)
        toolbar.addAction(self.mark_progress_action)
        
        self.extract_important_action = QAction(QIcon.fromTheme("edit-find"), "Extract Important Content", self)
        self.extract_important_action.triggered.connect(self._on_extract_important)
        toolbar.addAction(self.extract_important_action)
        
        return toolbar
        
    def _on_add_to_incremental_reading(self):
        """Add document to incremental reading queue."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            from PyQt6.QtWidgets import QInputDialog
            from core.spaced_repetition.incremental_reading import IncrementalReadingManager
            
            # Get priority from user
            priority, ok = QInputDialog.getDouble(
                self, "Reading Priority", 
                "Enter reading priority (0-100):",
                50, 0, 100, 1
            )
            
            if not ok:
                return
                
            # Add to incremental reading queue
            ir_manager = IncrementalReadingManager(self.db_session)
            result = ir_manager.add_document_to_queue(self.document_id, priority)
            
            if result:
                QMessageBox.information(
                    self, "Success", 
                    "Document added to incremental reading queue with priority %.1f" % priority
                )
            else:
                QMessageBox.warning(
                    self, "Error", 
                    "Failed to add document to incremental reading queue"
                )
                
        except Exception as e:
            logger.exception(f"Error adding to incremental reading: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _on_mark_reading_progress(self):
        """Mark reading progress for incremental reading."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            from PyQt6.QtWidgets import QInputDialog, QComboBox, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider
            from core.spaced_repetition.incremental_reading import IncrementalReadingManager
            from core.knowledge_base.models import IncrementalReading
            
            # Get current reading progress
            reading = self.db_session.query(IncrementalReading)\
                .filter(IncrementalReading.document_id == self.document_id)\
                .first()
                
            if not reading:
                result = QMessageBox.question(
                    self, "Incremental Reading", 
                    "This document is not in your incremental reading queue. Add it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if result == QMessageBox.StandardButton.Yes:
                    self._on_add_to_incremental_reading()
                return
                
            # Create custom dialog for rating reading session
            dialog = QDialog(self)
            dialog.setWindowTitle("Mark Reading Progress")
            layout = QVBoxLayout(dialog)
            
            # Current position
            current_pos = 0
            if hasattr(self, 'web_view') and self.web_view:
                # Get scroll position from web view
                self.web_view.page().runJavaScript(
                    "window.pageYOffset || document.documentElement.scrollTop || 0;",
                    lambda result: setattr(self, '_temp_scroll_pos', result)
                )
                QApplication.processEvents()
                current_pos = getattr(self, '_temp_scroll_pos', 0)
            
            # Add position display
            pos_layout = QHBoxLayout()
            pos_layout.addWidget(QLabel("Current Position:"))
            pos_label = QLabel(str(current_pos))
            pos_layout.addWidget(pos_label)
            layout.addLayout(pos_layout)
            
            # Add percent complete slider
            percent_layout = QHBoxLayout()
            percent_layout.addWidget(QLabel("Percent Complete:"))
            percent_slider = QSlider(Qt.Orientation.Horizontal)
            percent_slider.setRange(0, 100)
            percent_slider.setValue(int(reading.percent_complete))
            percent_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            percent_slider.setTickInterval(10)
            percent_layout.addWidget(percent_slider)
            percent_label = QLabel(f"{reading.percent_complete:.1f}%")
            percent_layout.addWidget(percent_label)
            layout.addLayout(percent_layout)
            
            # Update label when slider changes
            percent_slider.valueChanged.connect(
                lambda value: percent_label.setText(f"{value:.1f}%")
            )
            
            # Add rating selection
            rating_layout = QHBoxLayout()
            rating_layout.addWidget(QLabel("Rate this reading session:"))
            rating_combo = QComboBox()
            ratings = [
                "0 - Complete blackout",
                "1 - Barely remembered",
                "2 - Difficult, but remembered",
                "3 - Some effort needed",
                "4 - Easy recall",
                "5 - Perfect recall"
            ]
            rating_combo.addItems(ratings)
            rating_combo.setCurrentIndex(4)  # Default to "Easy recall"
            rating_layout.addWidget(rating_combo)
            layout.addLayout(rating_layout)
            
            # Add dialog buttons
            button_layout = QHBoxLayout()
            cancel_button = QPushButton("Cancel")
            cancel_button.clicked.connect(dialog.reject)
            save_button = QPushButton("Save Progress")
            save_button.clicked.connect(dialog.accept)
            save_button.setDefault(True)
            button_layout.addWidget(cancel_button)
            button_layout.addWidget(save_button)
            layout.addLayout(button_layout)
            
            # Show dialog
            if dialog.exec() == QDialog.DialogCode.Accepted:
                # Save progress
                ir_manager = IncrementalReadingManager(self.db_session)
                grade = rating_combo.currentIndex()
                percent = percent_slider.value()
                
                result = ir_manager.record_reading_session(
                    reading.id, current_pos, grade, percent
                )
                
                if result:
                    QMessageBox.information(
                        self, "Success", 
                        f"Reading progress saved. Next review scheduled for {reading.next_read_date.strftime('%Y-%m-%d')}"
                    )
                else:
                    QMessageBox.warning(
                        self, "Error", 
                        "Failed to save reading progress"
                    )
                
        except Exception as e:
            logger.exception(f"Error marking reading progress: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _on_extract_important(self):
        """Extract important content from document for learning."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            from PyQt6.QtWidgets import QInputDialog
            from core.spaced_repetition.incremental_reading import IncrementalReadingManager
            
            # Ask for number of extracts
            num_extracts, ok = QInputDialog.getInt(
                self, "Extract Content", 
                "Number of important sections to extract:",
                5, 1, 20, 1
            )
            
            if not ok:
                return
                
            # Extract important content
            ir_manager = IncrementalReadingManager(self.db_session)
            extracts = ir_manager.auto_extract_important_content(self.document_id, num_extracts)
            
            if extracts:
                QMessageBox.information(
                    self, "Success", 
                    f"Successfully extracted {len(extracts)} important sections from document."
                )
            else:
                QMessageBox.warning(
                    self, "Warning", 
                    "No important content could be extracted. Try using manual highlights."
                )
                
        except Exception as e:
            logger.exception(f"Error extracting important content: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
            
    def _on_highlight(self):
        """Create highlight from selected text."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            # Get selected text
            selected_text = None
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, use JavaScript to get selected text
                self.web_view.page().runJavaScript(
                    "window.getSelection().toString();",
                    lambda result: setattr(self, '_temp_selection', result)
                )
                
                # Process events to ensure JavaScript result is available
                for _ in range(10):  # Try a few iterations
                    QApplication.processEvents()
                    if hasattr(self, '_temp_selection'):
                        selected_text = self._temp_selection
                        break
                        
            elif hasattr(self, 'text_edit') and self.text_edit:
                # For text edit, use cursor
                selected_text = self.text_edit.textCursor().selectedText()
                
            if not selected_text or len(selected_text.strip()) < 5:
                QMessageBox.warning(
                    self, "Highlight", 
                    "Please select some text to highlight."
                )
                return
                
            # Create highlight
            from core.knowledge_base.models import WebHighlight
            
            highlight = WebHighlight(
                document_id=self.document_id,
                content=selected_text,
                created_date=datetime.utcnow()
            )
            
            # Get some context if available
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, try to get surrounding text
                self.web_view.page().runJavaScript(
                    """
                    (function() {
                        var sel = window.getSelection();
                        if (sel.rangeCount > 0) {
                            var range = sel.getRangeAt(0);
                            var contextNode = range.commonAncestorContainer;
                            if (contextNode.nodeType === Node.TEXT_NODE) {
                                contextNode = contextNode.parentNode;
                            }
                            return contextNode.textContent;
                        }
                        return "";
                    })();
                    """,
                    lambda result: setattr(highlight, 'context', result[:500])
                )
                # Process events to wait for JavaScript
                for _ in range(10):
                    QApplication.processEvents()
                
                # Also try to get XPath
                self.web_view.page().runJavaScript(
                    """
                    (function() {
                        var sel = window.getSelection();
                        if (sel.rangeCount > 0) {
                            var range = sel.getRangeAt(0);
                            var node = range.commonAncestorContainer;
                            if (node.nodeType === Node.TEXT_NODE) {
                                node = node.parentNode;
                            }
                            
                            var path = '';
                            while (node && node.nodeType === Node.ELEMENT_NODE) {
                                var name = node.nodeName.toLowerCase();
                                var index = 1;
                                var sibling = node.previousSibling;
                                while (sibling) {
                                    if (sibling.nodeType === Node.ELEMENT_NODE && 
                                        sibling.nodeName.toLowerCase() === name) {
                                        index++;
                                    }
                                    sibling = sibling.previousSibling;
                                }
                                path = '/' + name + '[' + index + ']' + path;
                                node = node.parentNode;
                            }
                            return path;
                        }
                        return "";
                    })();
                    """,
                    lambda result: setattr(highlight, 'xpath', result)
                )
                # Process events to wait for JavaScript
                for _ in range(10):
                    QApplication.processEvents()
                
                # Apply visual highlighting in the web view
                self.web_view.page().runJavaScript(
                    """
                    (function() {
                        var sel = window.getSelection();
                        if (sel.rangeCount > 0) {
                            var range = sel.getRangeAt(0);
                            
                            // Create highlight span
                            var highlightSpan = document.createElement('span');
                            highlightSpan.className = 'incrementum-highlight';
                            highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.4)';
                            highlightSpan.style.borderRadius = '2px';
                            
                            // Apply highlight
                            range.surroundContents(highlightSpan);
                            
                            // Clear selection
                            sel.removeAllRanges();
                            
                            return true;
                        }
                        return false;
                    })();
                    """
                )
            
            # Save highlight
            self.db_session.add(highlight)
            self.db_session.commit()
            
            QMessageBox.information(
                self, "Highlight", 
                "Highlight created successfully."
            )
                
        except Exception as e:
            logger.exception(f"Error creating highlight: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
            
    def _on_extract(self):
        """Create extract from selected text."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            # Get selected text
            selected_text = None
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, use JavaScript to get selected text
                self.web_view.page().runJavaScript(
                    "window.getSelection().toString();",
                    lambda result: setattr(self, '_temp_selection', result)
                )
                QApplication.processEvents()
                selected_text = getattr(self, '_temp_selection', None)
            elif hasattr(self, 'text_edit') and self.text_edit:
                # For text edit, use cursor
                selected_text = self.text_edit.textCursor().selectedText()
                
            if not selected_text or len(selected_text.strip()) < 5:
                QMessageBox.warning(
                    self, "Extract", 
                    "Please select some text to extract."
                )
                return
                
            # Create extract directly
            from core.knowledge_base.models import Extract
            
            extract = Extract(
                document_id=self.document_id,
                content=selected_text,
                created_date=datetime.utcnow(),
                priority=50
            )
            
            # Save extract
            self.db_session.add(extract)
            self.db_session.commit()
            
            QMessageBox.information(
                self, "Extract", 
                "Extract created successfully. You can find it in the Knowledge Base."
            )
                
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _show_context_menu(self, position):
        """Show document context menu."""
        if not hasattr(self, 'document_id') or not self.document_id:
            return
            
        menu = QMenu(self)
        
        # Add export actions
        export_menu = QMenu("Export", menu)
        
        # Export extracts action
        export_extracts_action = QAction("Export Extracts", export_menu)
        export_extracts_action.triggered.connect(self._export_extracts)
        export_menu.addAction(export_extracts_action)
        
        # Export SuperMemo HTML action
        export_sm_html_action = QAction("Export SuperMemo HTML", export_menu)
        export_sm_html_action.triggered.connect(self._export_supermemo_html)
        export_menu.addAction(export_sm_html_action)
        
        menu.addMenu(export_menu)
        
        # Add document management actions
        menu.addSeparator()
        
        # Other actions...
        
        menu.exec(self.mapToGlobal(position))

    def _export_supermemo_html(self):
        """Export document extracts and highlights as SuperMemo-compatible HTML."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            from PyQt6.QtWidgets import QFileDialog
            from core.spaced_repetition.sm_html_exporter import SuperMemoHTMLExporter
            
            # Ask for output directory
            output_dir = QFileDialog.getExistingDirectory(
                self, "Select Output Directory", os.path.expanduser("~")
            )
            
            if not output_dir:
                return
                
            # Export HTML
            exporter = SuperMemoHTMLExporter(self.db_session)
            result = exporter.export_document_extracts(self.document_id, output_dir)
            
            if result:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"SuperMemo HTML exported to:\n{result}"
                )
            else:
                QMessageBox.warning(
                    self, "Export Failed", 
                    "Failed to export SuperMemo HTML. Check if there are extracts or highlights."
                )
                
        except Exception as e:
            logger.exception(f"Error exporting SuperMemo HTML: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _add_supermemo_features(self, web_view):
        """Add SuperMemo-style incremental reading features to web view."""
        if not HAS_WEBENGINE or not isinstance(web_view, QWebEngineView):
            logger.warning("Cannot add SuperMemo features without WebEngine")
            return
            
        # Add JavaScript to enable SM-18 style incremental reading capabilities
        sm_script = """
        // SuperMemo SM-18 style incremental reading script
        
        // Initialize state
        let smState = {
            highlighting: false,
            startPoint: null,
            selectedText: '',
            lastSelection: null
        };
        
        // Add SuperMemo style toolbar
        function addSuperMemoToolbar() {
            // Create toolbar
            const toolbar = document.createElement('div');
            toolbar.id = 'sm-toolbar';
            toolbar.style.position = 'fixed';
            toolbar.style.bottom = '20px';
            toolbar.style.right = '20px';
            toolbar.style.zIndex = '1000';
            toolbar.style.backgroundColor = 'rgba(50, 50, 50, 0.7)';
            toolbar.style.padding = '5px';
            toolbar.style.borderRadius = '5px';
            toolbar.style.display = 'none';
            
            // Extract button
            const extractBtn = document.createElement('button');
            extractBtn.innerText = 'Extract';
            extractBtn.style.marginRight = '5px';
            extractBtn.style.cursor = 'pointer';
            extractBtn.onclick = function() {
                if (smState.selectedText) {
                    // Call back to Qt
                    if (typeof window.callbackHandler !== 'undefined') {
                        window.callbackHandler.extractText(smState.selectedText);
                    }
                    
                    // Visual feedback
                    extractBtn.style.backgroundColor = '#8f8';
                    setTimeout(() => {
                        extractBtn.style.backgroundColor = '';
                    }, 500);
                }
            };
            
            // Cloze button
            const clozeBtn = document.createElement('button');
            clozeBtn.innerText = 'Cloze';
            clozeBtn.style.marginRight = '5px';
            clozeBtn.style.cursor = 'pointer';
            clozeBtn.onclick = function() {
                if (smState.selectedText) {
                    // Call back to Qt
                    if (typeof window.callbackHandler !== 'undefined') {
                        window.callbackHandler.createCloze(smState.selectedText);
                    }
                    
                    // Visual feedback
                    clozeBtn.style.backgroundColor = '#8f8';
                    setTimeout(() => {
                        clozeBtn.style.backgroundColor = '';
                    }, 500);
                }
            };
            
            // Skip button
            const skipBtn = document.createElement('button');
            skipBtn.innerText = 'Skip';
            skipBtn.style.cursor = 'pointer';
            skipBtn.onclick = function() {
                // Call back to Qt
                if (typeof window.callbackHandler !== 'undefined') {
                    window.callbackHandler.skipItem();
                }
                
                // Visual feedback
                skipBtn.style.backgroundColor = '#f88';
                setTimeout(() => {
                    skipBtn.style.backgroundColor = '';
                }, 500);
            };
            
            // Add buttons to toolbar
            toolbar.appendChild(extractBtn);
            toolbar.appendChild(clozeBtn);
            toolbar.appendChild(skipBtn);
            
            // Add toolbar to document
            document.body.appendChild(toolbar);
            
            return toolbar;
        }
        
        // Track text selection
        document.addEventListener('selectionchange', function() {
            const selection = window.getSelection();
            const text = selection.toString().trim();
            
            // Store selection
            smState.selectedText = text;
            smState.lastSelection = selection;
            
            // Update toolbar visibility
            const toolbar = document.getElementById('sm-toolbar');
            if (toolbar) {
                if (text) {
                    // Position toolbar near selection
                    if (selection.rangeCount > 0) {
                        const range = selection.getRangeAt(0);
                        const rect = range.getBoundingClientRect();
                        
                        // Position near selection but ensure it's visible
                        toolbar.style.display = 'block';
                        toolbar.style.bottom = 'auto';
                        toolbar.style.right = 'auto';
                        
                        // Position above selection if there's room, otherwise below
                        if (rect.top > 100) {
                            toolbar.style.top = (rect.top - 40) + 'px';
                        } else {
                            toolbar.style.top = (rect.bottom + 10) + 'px';
                        }
                        
                        // Center horizontally on selection
                        toolbar.style.left = (rect.left + rect.width/2 - toolbar.offsetWidth/2) + 'px';
                    }
                } else {
                    toolbar.style.display = 'none';
                }
            }
            
            // Send selection to Qt if we have a callback handler
            if (text && typeof window.callbackHandler !== 'undefined') {
                window.callbackHandler.selectionChanged(text);
            }
        });
        
        // Run when document is loaded
        document.addEventListener('DOMContentLoaded', function() {
            // Add toolbar
            addSuperMemoToolbar();
            
            // Add keyboard shortcuts
            document.addEventListener('keydown', function(event) {
                // Handle Ctrl+E for extract
                if (event.ctrlKey && event.key === 'e') {
                    event.preventDefault();
                    const extractBtn = document.querySelector('#sm-toolbar button:nth-child(1)');
                    if (extractBtn) extractBtn.click();
                }
                
                // Handle Ctrl+C for cloze
                if (event.ctrlKey && event.key === 'c' && event.altKey) {
                    event.preventDefault();
                    const clozeBtn = document.querySelector('#sm-toolbar button:nth-child(2)');
                    if (clozeBtn) clozeBtn.click();
                }
                
                // Handle Ctrl+S for skip
                if (event.ctrlKey && event.key === 's') {
                    event.preventDefault();
                    const skipBtn = document.querySelector('#sm-toolbar button:nth-child(3)');
                    if (skipBtn) skipBtn.click();
                }
            });
        });
        
        // Initialize right away if document is already loaded
        if (document.readyState === 'complete' || document.readyState === 'interactive') {
            setTimeout(function() {
                addSuperMemoToolbar();
            }, 100);
        }
        """
        
        # Inject the SuperMemo JavaScript
        web_view.page().runJavaScript(sm_script)
        
        # Connect JavaScript to handle selection changes
        # This is already set up in _create_webview_and_setup
        
        logger.debug("Added SuperMemo features to web view")
    
    def _restore_position(self):
        """Restore previous reading position for the document."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                return
                
            # Check if we have a stored position for this document
            from core.knowledge_base.models import DocumentReadingPosition
            
            position = self.db_session.query(DocumentReadingPosition)\
                .filter_by(document_id=self.document_id)\
                .first()
                
            if not position:
                logger.debug(f"No reading position found for document {self.document_id}")
                return
                
            # Restore position based on content type
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, use JavaScript to set scroll position
                scroll_script = f"window.scrollTo(0, {position.position});"
                self.web_view.page().runJavaScript(scroll_script)
                logger.debug(f"Restored web view scroll position to {position.position}")
                
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
                # For widgets with scroll bars, set the value directly
                scrollbar = self.content_edit.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(position.position)
                    logger.debug(f"Restored scroll position to {position.position}")
                    
            # Also restore any view state like zoom factor
            if position.view_state:
                try:
                    # Parse the JSON view state
                    import json
                    view_state = json.loads(position.view_state)
                    
                    # Apply zoom factor if available
                    if 'zoom_factor' in view_state and hasattr(self, 'web_view') and self.web_view:
                        self.web_view.setZoomFactor(view_state['zoom_factor'])
                        logger.debug(f"Restored zoom factor to {view_state['zoom_factor']}")
                        
                except Exception as e:
                    logger.warning(f"Error restoring view state: {e}")
                    
            logger.debug(f"Successfully restored reading position for document {self.document_id}")
                
        except Exception as e:
            logger.exception(f"Error restoring reading position: {e}")
            # Continue without restoring position

    def _handle_webview_selection(self, text):
        """Handle text selection in the WebView."""
        if text and text.strip():
            self.selected_text = text.strip()
            logger.debug(f"Selected text in WebView: {text[:50]}...")
            
    def _on_create_extract(self):
        """Create an extract from the selected text."""
        try:
            if not self.selected_text or len(self.selected_text.strip()) < 5:
                logger.warning("No text selected for extract creation")
                return
                
            # Create extract
            from core.knowledge_base.models import Extract
            
            extract = Extract(
                document_id=self.document_id,
                content=self.selected_text,
                created_date=datetime.utcnow(),
                priority=50  # Default priority
            )
            
            # Save extract
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Emit the extract created signal
            self.extractCreated.emit(extract.id)
            
            logger.info(f"Created extract: {extract.id}")
            
            # Clear selection
            self.selected_text = ""
            
            return extract.id
            
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            return None
            
    def _handle_sm_extract_result(self, text):
        """Handle extract creation from SuperMemo JS callback."""
        self.selected_text = text
        extract_id = self._on_create_extract()
        
        if extract_id:
            logger.info(f"Created extract from SuperMemo: {extract_id}")
            
            # Show visual feedback in web view if available
            if hasattr(self, 'web_view') and self.web_view:
                feedback_script = """
                // Show extract confirmation
                const feedback = document.createElement('div');
                feedback.textContent = 'Extract created!';
                feedback.style.position = 'fixed';
                feedback.style.top = '20px';
                feedback.style.left = '50%';
                feedback.style.transform = 'translateX(-50%)';
                feedback.style.backgroundColor = 'rgba(0, 200, 0, 0.8)';
                feedback.style.color = 'white';
                feedback.style.padding = '10px 20px';
                feedback.style.borderRadius = '5px';
                feedback.style.zIndex = '9999';
                feedback.style.fontWeight = 'bold';
                
                document.body.appendChild(feedback);
                
                // Remove after 2 seconds
                setTimeout(() => {
                    feedback.style.opacity = '0';
                    feedback.style.transition = 'opacity 0.5s';
                    setTimeout(() => feedback.remove(), 500);
                }, 2000);
                """
                self.web_view.page().runJavaScript(feedback_script)
        
    def _handle_sm_cloze_result(self, text):
        """Handle cloze creation from SuperMemo JS callback."""
        try:
            if not text or len(text.strip()) < 5:
                logger.warning("Text too short for cloze creation")
                return
                
            # Create cloze
            from core.knowledge_base.models import Extract
            
            # Mark this as a cloze extract using a special prefix
            cloze_content = f"[CLOZE] {text}"
            
            extract = Extract(
                document_id=self.document_id,
                content=cloze_content,
                created_date=datetime.utcnow(),
                priority=50,  # Default priority
                extract_type="cloze"
            )
            
            # Save extract
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Emit the extract created signal
            self.extractCreated.emit(extract.id)
            
            logger.info(f"Created cloze extract: {extract.id}")
            
            # Show visual feedback in web view if available
            if hasattr(self, 'web_view') and self.web_view:
                feedback_script = """
                // Show cloze confirmation
                const feedback = document.createElement('div');
                feedback.textContent = 'Cloze created!';
                feedback.style.position = 'fixed';
                feedback.style.top = '20px';
                feedback.style.left = '50%';
                feedback.style.transform = 'translateX(-50%)';
                feedback.style.backgroundColor = 'rgba(0, 100, 200, 0.8)';
                feedback.style.color = 'white';
                feedback.style.padding = '10px 20px';
                feedback.style.borderRadius = '5px';
                feedback.style.zIndex = '9999';
                feedback.style.fontWeight = 'bold';
                
                document.body.appendChild(feedback);
                
                // Remove after 2 seconds
                setTimeout(() => {
                    feedback.style.opacity = '0';
                    feedback.style.transition = 'opacity 0.5s';
                    setTimeout(() => feedback.remove(), 500);
                }, 2000);
                """
                self.web_view.page().runJavaScript(feedback_script)
                
        except Exception as e:
            logger.exception(f"Error creating cloze: {e}")
            
    def _on_content_menu(self, position):
        """Show custom context menu for content."""
        menu = QMenu(self)
        
        # Only add actions if we have a document
        if hasattr(self, 'document_id') and self.document_id:
            # Get selected text
            has_selection = False
            selected_text = ""
            
            if hasattr(self, 'web_view') and self.web_view:
                # For WebView, get current selection via JavaScript
                self.web_view.page().runJavaScript(
                    "window.getSelection().toString();",
                    lambda result: setattr(self, '_temp_selection_result', result)
                )
                
                # Process events to ensure JavaScript result is available
                for _ in range(10):  # Try a few iterations
                    QApplication.processEvents()
                    if hasattr(self, '_temp_selection_result'):
                        selected_text = self._temp_selection_result
                        if selected_text and len(selected_text.strip()) > 0:
                            has_selection = True
                            self.selected_text = selected_text
                        break
            
            elif hasattr(self, 'text_edit') and self.text_edit:
                # For text edit widgets
                cursor = self.text_edit.textCursor()
                has_selection = cursor.hasSelection()
                if has_selection:
                    selected_text = cursor.selectedText()
                    self.selected_text = selected_text
            
            # Add extract action if text is selected
            if has_selection:
                extract_action = QAction("Extract Selection", self)
                extract_action.triggered.connect(self._on_extract)
                menu.addAction(extract_action)
                
                highlight_action = QAction("Highlight Selection", self)
                highlight_action.triggered.connect(self._on_highlight)
                menu.addAction(highlight_action)
                
                menu.addSeparator()
            
            # Add general document actions
            add_to_ir_action = QAction("Add to Incremental Reading", self)
            add_to_ir_action.triggered.connect(self._on_add_to_incremental_reading)
            menu.addAction(add_to_ir_action)
            
            # Add summarize action
            summarize_action = QAction("Summarize Document", self)
            summarize_action.triggered.connect(self.summarize_current_content)
            menu.addAction(summarize_action)
            
            menu.addSeparator()
        
        # Add clipboard actions
        if hasattr(self, 'selected_text') and self.selected_text:
            copy_action = QAction("Copy", self)
            copy_action.triggered.connect(
                lambda: QApplication.clipboard().setText(self.selected_text)
            )
            menu.addAction(copy_action)
        
        # Show menu if it has actions
        if not menu.isEmpty():
            menu.exec(self.mapToGlobal(position))
    
    def _set_error_message(self, message):
        """Display an error message in the content area."""
        error_label = QLabel(message)
        error_label.setWordWrap(True)
        error_label.setStyleSheet("color: red; padding: 20px;")
        self.content_layout.addWidget(error_label)
    
    def _export_extracts(self):
        """Export all extracts for the current document."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            from PyQt6.QtWidgets import QFileDialog
            
            # Ask for save location
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Extracts", "", "Text Files (*.txt);;HTML Files (*.html);;All Files (*)"
            )
            
            if not file_path:
                return
                
            # Get all extracts for this document
            from core.knowledge_base.models import Extract
            
            extracts = self.db_session.query(Extract)\
                .filter(Extract.document_id == self.document_id)\
                .order_by(Extract.created_date)\
                .all()
                
            if not extracts:
                QMessageBox.information(
                    self, "Export Extracts", 
                    "No extracts found for this document."
                )
                return
                
            # Format depends on file extension
            if file_path.lower().endswith('.html'):
                # Export as HTML
                html_content = f"""<!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <title>Extracts from {self.document.title}</title>
                    <style>
                        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }}
                        h1 {{ color: #333; }}
                        .extract {{ border: 1px solid #ddd; padding: 10px; margin: 10px 0; }}
                        .extract-date {{ color: #666; font-size: 0.8em; }}
                    </style>
                </head>
                <body>
                    <h1>Extracts from: {self.document.title}</h1>
                """
                
                for extract in extracts:
                    created_date = extract.created_date.strftime('%Y-%m-%d %H:%M:%S')
                    html_content += f"""
                    <div class="extract">
                        <div class="extract-content">{extract.content}</div>
                        <div class="extract-date">Created: {created_date}</div>
                    </div>
                    """
                
                html_content += """
                </body>
                </html>
                """
                
                # Write to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                    
            else:
                # Export as plain text
                text_content = f"EXTRACTS FROM: {self.document.title}\n"
                text_content += "=" * 50 + "\n\n"
                
                for extract in extracts:
                    created_date = extract.created_date.strftime('%Y-%m-%d %H:%M:%S')
                    text_content += f"{extract.content}\n\n"
                    text_content += f"Created: {created_date}\n"
                    text_content += "-" * 40 + "\n\n"
                
                # Write to file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
            
            QMessageBox.information(
                self, "Export Successful", 
                f"Extracts exported to {file_path}"
            )
                
        except Exception as e:
            logger.exception(f"Error exporting extracts: {e}")
            QMessageBox.warning(
                self, "Export Error", 
                f"An error occurred while exporting extracts: {str(e)}"
            )
