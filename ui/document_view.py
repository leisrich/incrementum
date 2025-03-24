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

from ui.document_position_manager import DocumentPositionManager
from ui.read_later_feature import ReadLaterManager, ReadLaterDialog
from ui.reading_stats_widget import ReadingStatsWidget, ReadingStatsDialog
from ui.position_autosave import DocumentPositionAutoSave

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QScrollArea, QSplitter, QTextEdit,
    QToolBar, QMenu, QMessageBox, QApplication, QDialog,
    QTabWidget, QLineEdit, QSizePolicy, QCheckBox, QSlider, 
    QInputDialog, QComboBox, QStyle, QTextEdit, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QUrl, QObject, QTimer, QPointF, QSize, QByteArray, QThread
from PyQt6.QtGui import QAction, QTextCursor, QColor, QTextCharFormat, QKeyEvent, QIntValidator, QIcon
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebChannel import QWebChannel
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False

# Separate try block for QtMultimedia since we've had issues with it
QT_MULTIMEDIA_AVAILABLE = False
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    QT_MULTIMEDIA_AVAILABLE = True
except (ImportError, RuntimeError) as multimedia_err:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import QtMultimedia: {multimedia_err}")

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
    navigate = pyqtSignal(str)  # navigation direction ("previous" or "next")
    
    def __init__(self, db_session, document_id=None):
        """Initialize DocumentView component."""
        super().__init__()
        
        # Store database session
        self.db_session = db_session
        
        # Document properties
        self.document_id = document_id
        self.document = None
        self.content_edit = None
        self.content_text = None
        self.selected_text = ""
        self.progress_marker = None
        self.zoom_level = 100
        self.view_mode = "Default"
        
        # Initialize web channel for communication with JavaScript
        if HAS_WEBENGINE:
            from PyQt6.QtWebChannel import QWebChannel
            self.web_channel = QWebChannel()
        
        # Create UI components
        self._create_ui()

        # Initialize position tracking
        self.position_manager = DocumentPositionManager(self)

        # Initialize Read Later manager
        self.read_later_manager = ReadLaterManager(self.db_session)

        # Initialize position auto-save
        self.position_autosave = DocumentPositionAutoSave(self)

        # Connect signals
        self.position_autosave.positionSaved.connect(self._on_position_saved)
        
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
        """Clear the content layout of any widgets."""
        try:
            # Stop audio playback if there's an audio player
            if hasattr(self, 'audio_player') and self.audio_player is not None:
                try:
                    # Stop playback and save position
                    self.audio_player.stop()
                    self.audio_player.save_position()
                    logger.info("Audio player stopped and position saved")
                except Exception as e:
                    logger.error(f"Error stopping audio player: {e}")
                
                # Clear reference to audio player
                self.audio_player = None

            # Clear the content layout
            if self.content_layout:
                while self.content_layout.count():
                    item = self.content_layout.takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.hide()
                        widget.deleteLater()
        except Exception as e:
            logger.error(f"Error clearing content layout: {e}")

    def cleanup(self):
        """Cleanup resources when document view is destroyed."""
        try:
            # Make a final position save before cleanup
            if hasattr(self, 'position_autosave'):
                try:
                    # Stop the timer first to prevent any more callbacks
                    if hasattr(self.position_autosave, 'timer') and self.position_autosave.timer:
                        self.position_autosave.timer.stop()
                    # Save current position one last time
                    self.position_autosave.save_position()
                except Exception as e:
                    logger.exception(f"Error stopping position autosave timer: {e}")

            # Stop timers
            if hasattr(self, 'position_manager'):
                self.position_manager.cleanup()

            # Save references to avoid creating new variables
            web_view_ref = None
            content_edit_ref = None
            
            if hasattr(self, 'web_view'):
                web_view_ref = self.web_view
                self.web_view = None
                
            if hasattr(self, 'content_edit'):  
                content_edit_ref = self.content_edit
                self.content_edit = None
                
            # Process events to ensure Qt handles the reference changes
            from PyQt6.QtCore import QCoreApplication
            QCoreApplication.processEvents()
            
            # Now safely delete any remaining references
            if web_view_ref is not None:
                try:
                    web_view_ref.deleteLater()
                except Exception:
                    # Already deleted, just ignore
                    pass
                    
            if content_edit_ref is not None and content_edit_ref != web_view_ref:
                try:
                    content_edit_ref.deleteLater()
                except Exception:
                    # Already deleted, just ignore
                    pass

            logger.debug("DocumentView cleanup completed")
        except Exception as e:
            logger.exception(f"Error during cleanup: {e}")

    def closeEvent(self, event):
        """Handle widget close event."""
        try:
            logger.debug(f"Closing document view for document ID: {self.document_id}")
            
            # Save the document position before closing
            if hasattr(self, 'document_id') and self.document_id:
                if hasattr(self, 'position_manager') and self.position_manager:
                    try:
                        # Force a final position save
                        self.position_manager.save_position()
                        logger.debug(f"Final position saved for document {self.document_id}")
                    except Exception as e:
                        logger.warning(f"Error saving final position for document {self.document_id}: {e}")
                
                # Clean up position autosave if present
                if hasattr(self, 'position_autosave') and self.position_autosave:
                    try:
                        self.position_autosave.stop()
                        logger.debug(f"Position autosave stopped for document {self.document_id}")
                    except Exception as e:
                        logger.warning(f"Error stopping position autosave: {e}")
            
            # Perform general cleanup
            self.cleanup()
            
        except Exception as e:
            logger.exception(f"Error during document view close: {e}")
        
        # Accept the close event
        event.accept()

    def _on_js_position_changed(self, position):
        """Handle position changed event from JavaScript."""
        # Update document position
        if hasattr(self, 'document') and self.document:
            self.document.position = position
            self.db_session.commit()

    def _update_bookmark_note(self, position, note):
        """Update note for bookmark at the specified position."""
        if not hasattr(self, 'read_later_manager'):
            return

        # Find and update bookmark
        for item in self.read_later_manager.read_later_items:
            if item.document_id == self.document_id and abs(item.position - position) < 100:
                item.note = note
                self.read_later_manager.save_items()

                # Update bookmark menu
                self.update_bookmark_menu()
                break

    def _remove_bookmark(self, position):
        """Remove bookmark at the specified position."""
        if not hasattr(self, 'read_later_manager'):
            return

        # Remove bookmark
        self.read_later_manager.remove_item(self.document_id, position)

        # Update bookmark menu
        self.update_bookmark_menu()

    def update_bookmark_menu(self):
        """Update the bookmark menu with current document bookmarks."""
        if not hasattr(self, 'bookmark_button') or not self.bookmark_button:
            return

        # Get menu
        menu = self.bookmark_button.menu()
        if not menu:
            return

        # Clear existing document bookmarks
        for action in menu.actions():
            if hasattr(action, 'is_bookmark') and action.is_bookmark:
                menu.removeAction(action)

        # Add current document bookmarks if available
        if hasattr(self, 'document_id') and self.document_id and hasattr(self, 'read_later_manager'):
            items = self.read_later_manager.get_items_for_document(self.document_id)

            if items:
                # Get document
                from core.knowledge_base.models import Document
                document = self.db_session.query(Document).get(self.document_id)

                # Add document header
                doc_header = QAction(f"Bookmarks for {document.title}", self.bookmark_button)
                doc_header.setEnabled(False)
                doc_header.is_bookmark = True
                menu.addAction(doc_header)

                # Add bookmark items
                for item in items:
                    # Create descriptive label
                    label = f"Position: {item.position:.0f}"
                    if item.note:
                        label = f"{label} - {item.note}"

                    # Create action
                    bookmark_action = QAction(label, self.bookmark_button)
                    bookmark_action.is_bookmark = True
                    bookmark_action.triggered.connect(lambda checked=False, pos=item.position: self._restore_read_later_position(pos))
                    menu.addAction(bookmark_action)
            else:
                # No bookmarks message
                no_bookmarks = QAction("No bookmarks for this document", self.bookmark_button)
                no_bookmarks.setEnabled(False)
                no_bookmarks.is_bookmark = True
                menu.addAction(no_bookmarks)
    
    def _update_vim_status_visibility(self):
        """Update the visibility of the Vim status bar based on Vim mode state."""
        self.vim_status_widget.setVisible(self.vim_key_handler.vim_mode)
    
    def _toggle_vim_mode(self):
        """Toggle Vim mode on/off."""
        is_enabled = self.vim_key_handler.toggle_vim_mode()
        self.vim_toggle_action.setChecked(is_enabled)
        self._update_vim_status_visibility()
    
    def keyPressEvent(self, event):
        """Handle key press events for document view."""
        # Check for 'n' key to navigate to next document
        if event.key() == Qt.Key.Key_N:
            self.navigate.emit("next")
            event.accept()
            return
        
        # Check for Ctrl+E shortcut for extract
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_E:
            self._on_extract()
            return
            
        # Check if Vim handler wants to handle this key
        if hasattr(self, 'vim_key_handler') and self.vim_key_handler.handle_key_event(event):
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
            
            return
            
        # Allow the parent class to handle the event
        super().keyPressEvent(event)
    
    def _create_webview_and_setup(self, html_content, base_url):
        """Create and setup a QWebEngineView with the provided HTML content."""
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        from PyQt6.QtCore import QTimer, QObject, pyqtSlot
        
        # Create web view
        webview = QWebEngineView()
        
        # Apply settings
        settings = webview.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PdfViewerEnabled, True)
        
        # Set content with base URL
        if base_url:
            webview.setHtml(html_content, base_url)
        else:
            webview.setHtml(html_content)
        
        # Create callback handler
        class SelectionHandler(QObject):
            @pyqtSlot(str)
            def selectionChanged(self, text):
                self.parent().selected_text = text
                if hasattr(self.parent(), 'extract_button'):
                    self.parent().extract_button.setEnabled(bool(text and len(text.strip()) > 0))
        
        # Add the handler to the page
        handler = SelectionHandler(self)
        webview.page().setWebChannel(self.web_channel)
        self.web_channel.registerObject("selectionHandler", handler)
        
        # First, we need to inject the QWebChannel JavaScript API
        # Get the path to qwebchannel.js
        qwebchannel_js = """
        // Define QWebChannel if needed
        if (typeof QWebChannel === 'undefined') {
            class QWebChannel {
                constructor(transport, callback) {
                    this.transport = transport;
                    this.objects = {};
                    
                    // Add the callback handler object
                    this.objects.selectionHandler = {
                        selectionChanged: function(text) {
                            if (window.qt && window.qt.selectionChanged) {
                                window.qt.selectionChanged(text);
                            }
                        }
                    };
                    
                    // Call the callback with this channel
                    if (callback) {
                        callback(this);
                    }
                }
            }
        }
        """
            
        # Inject a script to track selection changes
        selection_js = """
        // Global variable to store selection
        window.text_selection = '';
        
        // Track selection with standard event
        document.addEventListener('selectionchange', function() {
            var selection = window.getSelection();
            var text = selection.toString();
            if (text && text.trim().length > 0) {
                window.text_selection = text;
                
                // Try to call Qt callback if it exists
                if (window.qt && window.qt.selectionChanged) {
                    window.qt.selectionChanged(text);
                }
            }
        });
        
        // Track selection with mouse events for better reliability
        document.addEventListener('mouseup', function() {
            var selection = window.getSelection();
            var text = selection.toString();
            if (text && text.trim().length > 0) {
                window.text_selection = text;
                
                // Try to call Qt callback if it exists
                if (window.qt && window.qt.selectionChanged) {
                    window.qt.selectionChanged(text);
                }
            }
        });
        
        // Function to highlight extracted text
        window.highlightExtractedText = function(color) {
            var sel = window.getSelection();
            if (sel.rangeCount > 0) {
                var range = sel.getRangeAt(0);
                
                // Create highlight span
                var highlightSpan = document.createElement('span');
                highlightSpan.className = 'incrementum-highlight';
                
                // Set color based on parameter or default to yellow
                if (!color) color = 'yellow';
                
                switch(color) {
                    case 'yellow':
                        highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                        break;
                    case 'green':
                        highlightSpan.style.backgroundColor = 'rgba(0, 255, 0, 0.3)';
                        break;
                    case 'blue':
                        highlightSpan.style.backgroundColor = 'rgba(0, 191, 255, 0.3)';
                        break;
                    case 'pink':
                        highlightSpan.style.backgroundColor = 'rgba(255, 105, 180, 0.3)';
                        break;
                    case 'orange':
                        highlightSpan.style.backgroundColor = 'rgba(255, 165, 0, 0.3)';
                        break;
                    default:
                        highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                }
                
                highlightSpan.style.borderRadius = '2px';
                
                try {
                    // Apply highlight
                    range.surroundContents(highlightSpan);
                    
                    // Clear selection
                    sel.removeAllRanges();
                    
                    return true;
                } catch (e) {
                    console.error('Error highlighting text:', e);
                    return false;
                }
            }
            return false;
        };
        """
        
        # Inject JavaScript to connect with the handler
        connect_js = """
        // Connect with Qt web channel
        if (typeof QWebChannel === 'undefined') {
            console.error('QWebChannel is not defined. Using fallback method.');
            // Direct fallback for selection handling
            window.qt = {
                selectionChanged: function(text) {
                    // Handle in a simpler way
                    window.text_selection = text;
                }
            };
        } else {
            try {
                new QWebChannel(qt.webChannelTransport, function(channel) {
                    window.qt = channel.objects.selectionHandler;
                });
            } catch (e) {
                console.error('Error initializing QWebChannel:', e);
                // Fallback
                window.qt = {
                    selectionChanged: function(text) {
                        window.text_selection = text;
                    }
                };
            }
        }
        """
        
        # Add SuperMemo SM-18 style incremental reading capabilities
        self._add_supermemo_features(webview)
        
        # Inject scripts when the page is loaded - order matters!
        webview.loadFinished.connect(lambda ok: webview.page().runJavaScript(qwebchannel_js))
        webview.loadFinished.connect(lambda ok: webview.page().runJavaScript(selection_js))
        webview.loadFinished.connect(lambda ok: webview.page().runJavaScript(connect_js))
        
        # Add a method to manually get the current selection
        def check_selection():
            webview.page().runJavaScript(
                """
                (function() {
                    var selection = window.getSelection();
                    var text = selection.toString();
                    return text || window.text_selection || '';
                })();
                """,
                self._handle_webview_selection
            )
        
        # Store the method to check selection
        webview.check_selection = check_selection
        
        # Connect context menu request to check selection before showing menu
        webview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # Create a wrapper that first checks selection
        def context_menu_wrapper(pos):
            # Check for selection first
            check_selection()
            # Process events to ensure we get the selection
            QApplication.processEvents()
            # Small delay to ensure selection is processed
            QTimer.singleShot(50, lambda: self._on_content_menu(pos))
        
        webview.customContextMenuRequested.connect(context_menu_wrapper)
        
        # Disable default context menu for better control
        webview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
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
            # Save position of previous document if any
            if hasattr(self, 'document_id') and self.document_id and self.document_id != document_id:
                try:
                    if hasattr(self, 'position_autosave'):
                        self.position_autosave.save_position()
                    
                    # Also try to use the cleanup event to save position
                    self.closeEvent(None)
                except Exception as e:
                    logger.warning(f"Error saving position for previous document: {e}")
            
            # Keep any existing references alive
            if hasattr(self, 'webview'):
                self.keep_alive(self.webview)
            if hasattr(self, 'youtube_callback'):
                self.keep_alive(self.youtube_callback)
            if hasattr(self, 'audio_player'):
                self.keep_alive(self.audio_player)
                
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

            # Set up position tracking for this document
            if hasattr(self, 'position_manager'):
                self.position_manager.current_document_id = document_id

            if hasattr(self, 'position_autosave'):
                self.position_autosave.set_document(document_id)
                
            # Handle different document types
            if doc_type == "youtube":
                self._load_youtube()
            elif doc_type == "epub":
                success = self._load_epub(self.db_session, self.document)
                if not success:
                    # Fallback to HTML view if EPUB loading fails
                    logger.warning(f"Failed to load EPUB, falling back to HTML view")
                    self._load_html()
            elif doc_type == "pdf":
                self._load_pdf()
            elif doc_type == "html" or doc_type == "htm":
                self._load_html()
            elif doc_type == "txt":
                self._load_text()
            elif doc_type in ["mp3", "wav", "ogg", "flac", "m4a", "aac"]:
                self._load_audio()
            else:
                # Default to text view
                self._load_text()
            
            # Set window title to document title
            if hasattr(self, 'setWindowTitle') and callable(self.setWindowTitle):
                self.setWindowTitle(self.document.title)
                
            # Update read time counter if available
            if hasattr(self, 'reading_stats_widget'):
                try:
                    self.reading_stats_widget.set_document(self.document)
                except Exception as e:
                    logger.warning(f"Error initializing reading stats: {e}")
            
            # Restore position after a slight delay to ensure document is fully loaded
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(500, self._restore_position)
            
            # Update last accessed timestamp
            from datetime import datetime
            self.document.last_accessed = datetime.utcnow()
            self.db_session.commit()
            
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
                # Get the metadata file path from the document
                metadata_file = getattr(self.document, 'file_path', None)
                if not metadata_file:
                    logger.warning("No metadata file found for YouTube video")
                    raise ValueError("No metadata file found for YouTube video")
                
                # Create a transcript view widget with the correct parameters
                transcript_view = YouTubeTranscriptView(
                    self.db_session, 
                    self.document.id,  # Use document.id instead of document_id
                    metadata_file
                )
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
                # Show error message to user
                error_label = QLabel("Could not load video transcript. This might be because:\n"
                                   "1. The video has no captions\n"
                                   "2. Captions are disabled\n"
                                   "3. The video is private or unavailable\n"
                                   "4. The metadata file is missing")
                error_label.setWordWrap(True)
                error_label.setStyleSheet("color: #666; padding: 10px;")
                self.content_layout.addWidget(error_label)
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
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtCore import QUrl, QObject, pyqtSlot, QTimer
            content_edit = QWebEngineView()
            
            # Load the EPUB into the handler
            try:
                from core.document_processor.handlers.epub_handler import EPUBHandler
                # Load the file data and prepare it for the webview
                epub_handler = EPUBHandler()
                content_results = epub_handler.extract_content(document.file_path)
                html_content = content_results['html']
                
                # Process the HTML content
                html_content = self._inject_javascript_libraries(html_content)
                
                # Set up the web channel for JavaScript communication
                if not hasattr(self, 'web_channel'):
                    from PyQt6.QtWebChannel import QWebChannel
                    self.web_channel = QWebChannel()
                
                # Set the EPUB content to the web view
                content_edit.setHtml(html_content, QUrl.fromLocalFile(document.file_path))
                
                # Store the web view for later use (important for context menu)
                self.web_view = content_edit
                self.content_edit = content_edit
                

                # Add to keep alive to prevent garbage collection
                self.keep_alive(content_edit)

                # Set up the selection handling and context menu
                from PyQt6.QtCore import QObject, pyqtSlot
                
                class SelectionHandler(QObject):
                    @pyqtSlot(str)
                    def selectionChanged(self, text):
                        self.parent().selected_text = text
                        if hasattr(self.parent(), 'extract_button'):
                            self.parent().extract_button.setEnabled(bool(text and len(text.strip()) > 0))
                
                # Add the handler to the page
                handler = SelectionHandler(self)
                content_edit.page().setWebChannel(self.web_channel)
                self.web_channel.registerObject("selectionHandler", handler)
                
                # Add JavaScript files for enhanced features
                js_files = [
                    'position_tracking.js',
                    'visual_bookmarks.js',
                    'timeline_view.js'
                ]

                for js_file in js_files:
                    js_path = os.path.join(os.path.dirname(__file__), js_file)
                    if os.path.exists(js_path):
                        with open(js_path, 'r') as f:
                            script = f.read()
                            content_edit.page().runJavaScript(script)
                    else:
                        logger.warning(f"JavaScript file not found: {js_path}")

                # Initialize with document ID
                doc_id_script = f"document.documentElement.setAttribute('data-document-id', '{self.document_id}');"
                content_edit.page().runJavaScript(doc_id_script)

                # Set up communication handlers for JavaScript features
                class WebFeaturesHandler(QObject):
                    """Handler for JavaScript communication."""
                    
                    @pyqtSlot(float)
                    def positionChanged(self, position):
                        """Handle position changed event from JavaScript."""
                        self.parent()._on_js_position_changed(position)
                    
                    @pyqtSlot(float)
                    def addBookmark(self, position):
                        """Handle add bookmark request from JavaScript."""
                        self.parent()._create_read_later_item(position)
                    
                    @pyqtSlot(float, str)
                    def updateBookmark(self, position, note):
                        """Handle update bookmark request from JavaScript."""
                        self.parent()._update_bookmark_note(position, note)
                    
                    @pyqtSlot(float)
                    def removeBookmark(self, position):
                        """Handle remove bookmark request from JavaScript."""
                        self.parent()._remove_bookmark(position)

                # Create handler and register with web channel
                handler = WebFeaturesHandler(self)
                if not hasattr(self, 'web_channel'):
                    from PyQt6.QtWebChannel import QWebChannel
                    self.web_channel = QWebChannel()
                self.web_channel.registerObject("qtHandler", handler)

                # First, inject the QWebChannel JavaScript API fallback
                qwebchannel_js = """
                // Define QWebChannel if needed
                if (typeof QWebChannel === 'undefined') {
                    console.log('QWebChannel not found, creating fallback implementation');
                    class QWebChannel {
                        constructor(transport, callback) {
                            console.log('QWebChannel fallback created');
                            this.transport = transport;
                            this.objects = {};
                            
                            // Add the callback handler object
                            this.objects.selectionHandler = {
                                selectionChanged: function(text) {
                                    console.log('Selection changed in fallback handler:', text);
                                    if (window.qt && window.qt.selectionChanged) {
                                        window.qt.selectionChanged(text);
                                    }
                                }
                            };
                            
                            // Call the callback with this channel
                            if (callback) {
                                setTimeout(function() {
                                    callback(this);
                                }.bind(this), 0);
                            }
                        }
                    }
                    
                    // Create global namespace
                    window.qt = {
                        webChannelTransport: {},
                        selectionChanged: function(text) {
                            console.log('Selection fallback called with:', text);
                            window.text_selection = text;
                        }
                    };
                    
                    console.log('QWebChannel fallback implementation complete');
                }
                
                // Ensure QWebChannel is properly initialized
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('DOM loaded, checking QWebChannel');
                    if (typeof QWebChannel === 'undefined') {
                        console.warn('QWebChannel still not defined after DOMContentLoaded');
                    } else {
                        console.log('QWebChannel is available');
                    }
                });
                """
                
                # Inject custom JavaScript for selection handling
                selection_js = """
                // Global variable to store selection
                window.text_selection = '';
                
                // Track selection with standard event
                document.addEventListener('selectionchange', function() {
                    var selection = window.getSelection();
                    var text = selection.toString();
                    if (text && text.trim().length > 0) {
                        window.text_selection = text;
                        
                        // Try to call Qt callback if it exists
                        if (window.qt && window.qt.selectionChanged) {
                            window.qt.selectionChanged(text);
                        }
                    }
                });
                
                // Track selection with mouse events for better reliability
                document.addEventListener('mouseup', function() {
                    var selection = window.getSelection();
                    var text = selection.toString();
                    if (text && text.trim().length > 0) {
                        window.text_selection = text;
                        
                        // Try to call Qt callback if it exists
                        if (window.qt && window.qt.selectionChanged) {
                            window.qt.selectionChanged(text);
                        }
                    }
                });
                
                // Function to highlight extracted text
                window.highlightExtractedText = function(color) {
                    var sel = window.getSelection();
                    if (sel.rangeCount > 0) {
                        var range = sel.getRangeAt(0);
                        
                        // Create highlight span
                        var highlightSpan = document.createElement('span');
                        highlightSpan.className = 'incrementum-highlight';
                        
                        // Set color based on parameter or default to yellow
                        if (!color) color = 'yellow';
                        
                        switch(color) {
                            case 'yellow':
                                highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                break;
                            case 'green':
                                highlightSpan.style.backgroundColor = 'rgba(0, 255, 0, 0.3)';
                                break;
                            case 'blue':
                                highlightSpan.style.backgroundColor = 'rgba(0, 191, 255, 0.3)';
                                break;
                            case 'pink':
                                highlightSpan.style.backgroundColor = 'rgba(255, 105, 180, 0.3)';
                                break;
                            case 'orange':
                                highlightSpan.style.backgroundColor = 'rgba(255, 165, 0, 0.3)';
                                break;
                            default:
                                highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                        }
                        
                        highlightSpan.style.borderRadius = '2px';
                        
                        try {
                            // Apply highlight
                            range.surroundContents(highlightSpan);
                            
                            // Clear selection
                            sel.removeAllRanges();
                            
                            return true;
                        } catch (e) {
                            console.error('Error highlighting text:', e);
                            return false;
                        }
                    }
                    return false;
                };
                """
                
                # Inject JavaScript to connect with the handler
                connect_js = """
                // Connect with Qt web channel
                if (typeof QWebChannel === 'undefined') {
                    console.error('QWebChannel is not defined. Using fallback method.');
                    // Direct fallback for selection handling
                    window.qt = window.qt || {};
                    window.qt.selectionChanged = function(text) {
                        // Handle in a simpler way
                        console.log('Fallback selection handler called with:', text);
                        window.text_selection = text;
                    };
                } else {
                    try {
                        console.log('Attempting to initialize QWebChannel with transport');
                        if (!qt.webChannelTransport) {
                            console.warn('webChannelTransport not found, creating dummy');
                            qt.webChannelTransport = {};
                        }
                        
                        new QWebChannel(qt.webChannelTransport, function(channel) {
                            console.log('QWebChannel initialized successfully');
                            window.qt = channel.objects.selectionHandler;
                            console.log('Selection handler registered:', window.qt);
                        });
                    } catch (e) {
                        console.error('Error initializing QWebChannel:', e);
                        // Fallback
                        window.qt = window.qt || {};
                        window.qt.selectionChanged = function(text) {
                            console.log('Error fallback selection handler called with:', text);
                            window.text_selection = text;
                        };
                    }
                }
                
                // Global function to check if selection handling is working
                window.checkSelectionHandler = function() {
                    console.log('Qt object:', window.qt);
                    console.log('Current selection:', window.text_selection);
                    return {
                        qt: !!window.qt,
                        selection: window.text_selection,
                        channelDefined: (typeof QWebChannel !== 'undefined')
                    };
                };
                """
                
                # Add SuperMemo SM-18 style incremental reading capabilities
                self._add_supermemo_features(content_edit)
                
                # Inject the scripts after the page has loaded - order matters!
                content_edit.loadFinished.connect(lambda ok: content_edit.page().runJavaScript(qwebchannel_js))
                # Add a small delay to ensure the QWebChannel script has time to execute
                content_edit.loadFinished.connect(lambda ok: QTimer.singleShot(100, lambda: content_edit.page().runJavaScript(selection_js)))
                content_edit.loadFinished.connect(lambda ok: QTimer.singleShot(200, lambda: content_edit.page().runJavaScript(connect_js)))
                
                # Add a diagnostic check after a delay
                content_edit.loadFinished.connect(lambda ok: QTimer.singleShot(500, lambda: content_edit.page().runJavaScript(
                    "window.checkSelectionHandler ? window.checkSelectionHandler() : 'Not available'",
                    lambda result: logger.debug(f"Selection handler check: {result}")
                )))
                
                # Set up context menu
                content_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                
                # Create a method to check for selection
                def check_selection():
                    content_edit.page().runJavaScript(
                        """
                        (function() {
                            var selection = window.getSelection();
                            var text = selection.toString();
                            return text || window.text_selection || '';
                        })();
                        """,
                        self._handle_webview_selection
                    )
                
                # Store the method for later use
                content_edit.check_selection = check_selection
                
                # Connect context menu
                def context_menu_wrapper(pos):
                    # Check for selection first
                    check_selection()
                    # Process events to ensure we get the selection
                    QApplication.processEvents()
                    # Small delay to ensure selection is processed
                    QTimer.singleShot(50, lambda: self._on_content_menu(pos))
                
                content_edit.customContextMenuRequested.connect(context_menu_wrapper)
                
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

    def _on_add_read_later(self):
        """Add current position to Read Later."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return

            # Get current position
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, get scroll position using JavaScript
                self.web_view.page().runJavaScript(
                    "window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;",
                    lambda result: self._create_read_later_item(result)
                )
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
                # For text edit or other scrollable widgets
                scrollbar = self.content_edit.verticalScrollBar()
                position = scrollbar.value()
                self._create_read_later_item(position)
            elif hasattr(self, 'audio_player') and hasattr(self.audio_player, 'audioPosition'):
                # For audio player
                position = self.audio_player.audioPosition()
                self._create_read_later_item(position)
            elif hasattr(self, 'pdf_view') and hasattr(self.pdf_view, 'currentPage'):
                # For PDF viewer
                position = self.pdf_view.currentPage()
                self._create_read_later_item(position)
            else:
                QMessageBox.warning(
                    self, "Read Later",
                    "Unable to determine reading position for this document type."
                )

        except Exception as e:
            logger.exception(f"Error adding to Read Later: {e}")
            QMessageBox.warning(
                self, "Error",
                f"An error occurred: {str(e)}"
            )

    def _create_read_later_item(self, position):
        """Create a Read Later item with the given position."""
        try:
            # Ask for note
            note, ok = QInputDialog.getText(
                self,
                "Add to Read Later",
                "Enter a note for this position (optional):",
                text=""
            )

            if not ok:
                return

            # Add to manager
            item = self.read_later_manager.add_item(
                document_id=self.document_id,
                position=position,
                note=note if note else None
            )

            # Add visual bookmark if in web view
            if hasattr(self, 'web_view') and self.web_view:
                # Add visual bookmark with JavaScript
                script = f"""
                if (typeof addVisualBookmark === 'function') {{
                    addVisualBookmark({position}, "{note.replace('"', '')}");
                    true;
                }} else {{
                    false;
                }}
                """
                self.web_view.page().runJavaScript(script)

            QMessageBox.information(
                self, "Read Later",
                "Position saved for reading later."
            )

        except Exception as e:
            logger.exception(f"Error creating Read Later item: {e}")
            QMessageBox.warning(
                self, "Error",
                f"An error occurred: {str(e)}"
            )

    def _on_show_read_later_items(self):
        """Show Read Later items dialog."""
        try:
            from read_later_feature import ReadLaterDialog

            dialog = ReadLaterDialog(self.db_session, self)
            dialog.itemSelected.connect(self._on_read_later_item_selected)
            dialog.exec()

        except Exception as e:
            logger.exception(f"Error showing Read Later items: {e}")
            QMessageBox.warning(
                self, "Error",
                f"An error occurred: {str(e)}"
            )

    def _on_read_later_item_selected(self, document_id, position):
        """Handle selection of a Read Later item."""
        try:
            # Check if the document is already loaded
            if hasattr(self, 'document_id') and self.document_id == document_id:
                # Just restore position
                self._restore_read_later_position(position)
            else:
                # Load the document
                self.load_document(document_id)

                # Set a timer to restore position after document is loaded
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(500, lambda: self._restore_read_later_position(position))

        except Exception as e:
            logger.exception(f"Error loading Read Later item: {e}")
            QMessageBox.warning(
                self, "Error",
                f"An error occurred: {str(e)}"
            )

    def _restore_read_later_position(self, position):
        """Restore a specific position for the current document."""
        if hasattr(self, 'web_view') and self.web_view:
            # For web view, use JavaScript to set scroll position
            script = f"""
            if (typeof restoreDocumentPosition === 'function') {{
                restoreDocumentPosition({position});
            }} else {{
                window.scrollTo(0, {position});
            }}
            """
            self.web_view.page().runJavaScript(script)

        elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
            # For scrollable widgets
            scrollbar = self.content_edit.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(position)

        elif hasattr(self, 'audio_player') and hasattr(self.audio_player, 'setAudioPosition'):
            # For audio player
            self.audio_player.setAudioPosition(position)

        elif hasattr(self, 'pdf_view') and hasattr(self.pdf_view, 'goToPage'):
            # For PDF viewer
            self.pdf_view.goToPage(int(position))

    def _on_show_reading_stats(self):
        """Show reading statistics dialog."""
        try:
            dialog = ReadingStatsDialog(self, self)
            dialog.exec()

        except Exception as e:
            logger.exception(f"Error showing reading statistics: {e}")
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
            
            # Get the selected highlight color
            color_name = self.highlight_color_combo.currentData()
                
            # Get selected text
            selected_text = None
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, use JavaScript to get selected text
                script = f"""
                (function() {{
                    var selection = window.getSelection();
                    var text = selection.toString();
                    if (text && text.trim().length > 0) {{
                        // Highlight if we have a SuperMemo script
                        if (typeof highlightExtractedText === 'function') {{
                            highlightExtractedText('{color_name}');
                        }}
                        return text;
                    }}
                    return '';
                }})();
                """
                self.web_view.page().runJavaScript(
                    script,
                    lambda result: self._process_extracted_text(result, color_name)
                )
                # Continue processing in the callback (_process_extracted_text)
                return
            elif hasattr(self, 'text_edit') and self.text_edit:
                # For text edit, use cursor
                selected_text = self.text_edit.textCursor().selectedText()
                self._process_extracted_text(selected_text, color_name)
                
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
            
    def _process_extracted_text(self, selected_text, color_name='yellow'):
        """Process text after extraction from web view or text edit."""
        try:
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
            
            # Also create a WebHighlight with the specified color
            from core.knowledge_base.models import WebHighlight
            
            highlight = WebHighlight(
                document_id=self.document_id,
                content=selected_text,
                created_date=datetime.utcnow(),
                color=color_name
            )
            
            # Save highlight
            self.db_session.add(highlight)
            self.db_session.commit()
            
            # Emit signal for extract created
            self.extractCreated.emit(extract.id)
            
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
                    
                    // Highlight the extracted text
                    highlightExtractedText();
                    
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
        
        // Function to highlight extracted text
        function highlightExtractedText() {
            if (!smState.lastSelection || !smState.lastSelection.rangeCount) return;
            
            const range = smState.lastSelection.getRangeAt(0);
            const span = document.createElement('span');
            span.className = 'extracted-text-highlight';
            span.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
            span.style.borderRadius = '2px';
            
            try {
                range.surroundContents(span);
                // Keep the selection active
                smState.lastSelection.removeAllRanges();
                smState.lastSelection.addRange(range);
            } catch (e) {
                console.error('Error highlighting text:', e);
            }
        }
        
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
            document = self.db_session.query(Document).get(self.document_id)
            
            if not document or document.position is None:
                logger.debug(f"No reading position found for document {self.document_id}")
                return
                
            position = document.position
            logger.info(f"Restoring position {position} for document {self.document.title}")
                
            # Function to verify restoration was successful
            def verify_restoration(success=True):
                if success:
                    logger.info(f"Successfully restored position for {self.document.title}")
                else:
                    logger.warning(f"Failed to restore position for {self.document.title}")
                
            # Restore position based on content type
            doc_type = document.content_type.lower() if hasattr(document, 'content_type') and document.content_type else "text"
            
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, use JavaScript to set scroll position with a delay
                # to ensure document is fully loaded
                from PyQt6.QtCore import QTimer
                
                def apply_scroll():
                    # First simple scroll attempt
                    scroll_script = f"window.scrollTo(0, {document.position});"
                    self.web_view.page().runJavaScript(scroll_script)
                    
                    # Enhanced scroll for reliability
                    enhanced_script = f"""
                    (function() {{
                        // First attempt simple scroll
                        window.scrollTo(0, {position});
                        
                        // Then force scroll on all potential elements
                        var scrollElements = [
                            document.documentElement,
                            document.body,
                            document.querySelector('html'),
                            document.querySelector('body'),
                            document.querySelector('main'),
                            document.querySelector('.content'),
                            document.querySelector('#content'),
                            document.querySelector('.main')
                        ];
                        
                        for (var i = 0; i < scrollElements.length; i++) {{
                            var el = scrollElements[i];
                            if (el) {{
                                el.scrollTop = {position};
                            }}
                        }}
                        
                        // Get actual scroll position to verify
                        return window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;
                    }})();
                    """
                    self.web_view.page().runJavaScript(enhanced_script, lambda result: verify_restoration(abs(result - position) < 50))
                    
                    logger.debug(f"Applied web scroll to position {position}")
                
                # First attempt immediately
                apply_scroll()
                
                # Multiple attempts with increasing delays for complex documents
                QTimer.singleShot(500, apply_scroll)
                QTimer.singleShot(1000, apply_scroll)
                QTimer.singleShot(2000, apply_scroll)
                
            elif doc_type == "pdf" and hasattr(self, 'content_edit'):
                # For PDF content
                try:
                    # Try different PDF interfaces
                    if hasattr(self.content_edit, 'set_view_state'):
                        # For newer PDF view with state management
                        state = {'page': int(position)}
                        if hasattr(document, 'extra_info') and document.extra_info:
                            try:
                                import json
                                extra_info = json.loads(document.extra_info)
                                if 'pdf_state' in extra_info:
                                    # Merge with saved PDF state (zoom, position within page)
                                    state.update(extra_info['pdf_state'])
                            except Exception as e:
                                logger.warning(f"Error parsing PDF extra info: {e}")
                                
                        self.content_edit.set_view_state(state)
                        verify_restoration()
                    elif hasattr(self.content_edit, 'goToPage'):
                        # Direct page navigation
                        self.content_edit.goToPage(int(position))
                        verify_restoration()
                    elif hasattr(self.content_edit, '_on_page_requested'):
                        # Via event
                        self.content_edit._on_page_requested(int(position))
                        verify_restoration()
                    else:
                        logger.warning(f"PDF view doesn't support position restoration")
                        verify_restoration(False)
                except Exception as e:
                    logger.exception(f"Error restoring PDF position: {e}")
                    verify_restoration(False)
                
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
                # For widgets with scroll bars, set the value directly
                try:
                    scrollbar = self.content_edit.verticalScrollBar()
                    if scrollbar:
                        scrollbar.setValue(int(position))
                        # Try again after a delay to handle layout changes
                        QTimer.singleShot(500, lambda: scrollbar.setValue(int(position)))
                        verify_restoration(True)
                    else:
                        logger.warning(f"No scrollbar found for content editor")
                        verify_restoration(False)
                except Exception as e:
                    logger.exception(f"Error restoring scrollbar position: {e}")
                    verify_restoration(False)
            
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'setAudioPosition'):
                # For audio content
                try:
                    self.content_edit.setAudioPosition(position)
                    verify_restoration(True)
                except Exception as e:
                    logger.exception(f"Error restoring audio position: {e}")
                    verify_restoration(False)
                    
            else:
                logger.warning(f"Unsupported content type for position restoration: {doc_type}")
                verify_restoration(False)
                
        except Exception as e:
            logger.exception(f"Error restoring reading position: {e}")
            # Continue without restoring position


    def _handle_webview_selection(self, text):
        """Handle text selection in the WebView."""
        if text and text.strip():
            self.selected_text = text.strip()
            logger.debug(f"Selected text in WebView: {text[:50]}...")

    def _on_position_saved(self, document_id, position):
        """Handle position saved event."""
        # This can be used for UI feedback if needed
        pass
            
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
        try:
            menu = QMenu(self)
            
            # Check if we have selected text
            has_selection = False
            selected_text = ""
            
            # Define build_menu function first, before it's used
            def build_menu(has_selection, selected_text):
                # Store the selected text for use in action handlers
                self.selected_text = selected_text if has_selection else ""
                
                # Add extract action if text is selected
                if has_selection:
                    extract_action = QAction("Extract Selection", self)
                    extract_action.triggered.connect(self._extract_from_context_menu)
                    menu.addAction(extract_action)
                    
                    # Add highlight action with color submenu
                    highlight_menu = QMenu("Highlight Selection", menu)
                    
                    # Add color options
                    yellow_action = QAction("Yellow", self)
                    yellow_action.triggered.connect(lambda: self._highlight_with_color("yellow"))
                    highlight_menu.addAction(yellow_action)
                    
                    green_action = QAction("Green", self)
                    green_action.triggered.connect(lambda: self._highlight_with_color("green"))
                    highlight_menu.addAction(green_action)
                    
                    blue_action = QAction("Blue", self)
                    blue_action.triggered.connect(lambda: self._highlight_with_color("blue"))
                    highlight_menu.addAction(blue_action)
                    
                    pink_action = QAction("Pink", self)
                    pink_action.triggered.connect(lambda: self._highlight_with_color("pink"))
                    highlight_menu.addAction(pink_action)
                    
                    orange_action = QAction("Orange", self)
                    orange_action.triggered.connect(lambda: self._highlight_with_color("orange"))
                    highlight_menu.addAction(orange_action)

                    # Add Read Later option
                    read_later_action = QAction("Read Later (🔖)", self)
                    read_later_action.triggered.connect(self._on_add_read_later)
                    menu.addAction(read_later_action)

                    # Add reading stats option
                    stats_action = QAction("Reading Statistics 📊", self)
                    stats_action.triggered.connect(self._on_show_reading_stats)
                    menu.addAction(stats_action)
                    
                    menu.addMenu(highlight_menu)
                    
                    # Add separator
                    menu.addSeparator()
                else:
                    # If we're in a WebView and there's no selection, add a message
                    if hasattr(self, 'web_view') and self.web_view:
                        info_action = QAction("Select text to extract", self)
                        info_action.setEnabled(False)
                        menu.addAction(info_action)
                        menu.addSeparator()
                
                # Add document actions
                add_to_ir_action = QAction("Add to Incremental Reading", self)
                add_to_ir_action.triggered.connect(self._on_add_to_incremental_reading)
                menu.addAction(add_to_ir_action)
                
                mark_progress_action = QAction("Mark Reading Progress", self)
                mark_progress_action.triggered.connect(self._on_mark_reading_progress)
                menu.addAction(mark_progress_action)
                
                # Add zoom actions
                menu.addSeparator()
                
                zoom_in_action = QAction("Zoom In", self)
                zoom_in_action.triggered.connect(self._on_zoom_in)
                menu.addAction(zoom_in_action)
                
                zoom_out_action = QAction("Zoom Out", self)
                zoom_out_action.triggered.connect(self._on_zoom_out)
                menu.addAction(zoom_out_action)
            
            # Define context_menu_wrapper after build_menu is defined
            def context_menu_wrapper(text):
                if text and text.strip():
                    self.selected_text = text.strip()
                    has_selection = True
                    build_menu(True, text)
                    menu.exec(self.mapToGlobal(position))
                else:
                    # No selection, show basic menu
                    build_menu(False, "")
                    menu.exec(self.mapToGlobal(position))
            
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, get selection using JavaScript
                def check_selection():
                    script = """
                    (function() {
                        var selection = window.getSelection();
                        var text = selection.toString();
                        if (text && text.trim().length > 0) {
                            return text;
                        }
                        return '';
                    })();
                    """
                    self.web_view.page().runJavaScript(
                        script,
                        lambda result: context_menu_wrapper(result)
                    )
                
                check_selection()
                return  # will continue in the callback
                
            elif hasattr(self, 'content_edit') and self.content_edit:
                # For QTextEdit, check cursor selection
                if hasattr(self.content_edit, 'textCursor'):
                    cursor = self.content_edit.textCursor()
                    selected_text = cursor.selectedText()
                    has_selection = bool(selected_text and selected_text.strip())
            
            # Build menu directly for non-web view contexts
            build_menu(has_selection, selected_text)
            menu.exec(self.mapToGlobal(position))
            
        except Exception as e:
            logger.exception(f"Error showing context menu: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while showing the context menu: {str(e)}"
            )

    def _highlight_with_color(self, color):
        """Highlight the selected text with the specified color."""
        try:
            # Set the color in the dropdown to match
            for i in range(self.highlight_color_combo.count()):
                if self.highlight_color_combo.itemData(i) == color:
                    self.highlight_color_combo.setCurrentIndex(i)
                    break
                    
            # Now highlight with this color
            if hasattr(self, 'web_view') and self.web_view:
                # Apply highlight with JavaScript
                script = f"""
                (function() {{
                    var selection = window.getSelection();
                    var text = selection.toString();
                    if (text && text.trim().length > 0) {{
                        // Create highlight span
                        var sel = window.getSelection();
                        if (sel.rangeCount > 0) {{
                            var range = sel.getRangeAt(0);
                            
                            // Create highlight span
                            var highlightSpan = document.createElement('span');
                            highlightSpan.className = 'incrementum-highlight';
                            
                            // Set color based on selection
                            switch('{color}') {{
                                case 'yellow':
                                    highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                    break;
                                case 'green':
                                    highlightSpan.style.backgroundColor = 'rgba(0, 255, 0, 0.3)';
                                    break;
                                case 'blue':
                                    highlightSpan.style.backgroundColor = 'rgba(0, 191, 255, 0.3)';
                                    break;
                                case 'pink':
                                    highlightSpan.style.backgroundColor = 'rgba(255, 105, 180, 0.3)';
                                    break;
                                case 'orange':
                                    highlightSpan.style.backgroundColor = 'rgba(255, 165, 0, 0.3)';
                                    break;
                                default:
                                    highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                            }}
                            
                            highlightSpan.style.borderRadius = '2px';
                            
                            try {{
                                // Apply highlight
                                range.surroundContents(highlightSpan);
                                
                                // Clear selection
                                sel.removeAllRanges();
                                
                                return text;
                            }} catch (e) {{
                                console.error('Error highlighting text:', e);
                                return '';
                            }}
                        }}
                    }}
                    return '';
                }})();
                """
                self.web_view.page().runJavaScript(
                    script,
                    lambda result: self._process_highlight_text(result, color)
                )
            elif hasattr(self, 'text_edit') and self.text_edit:
                cursor = self.text_edit.textCursor()
                if cursor.hasSelection():
                    # Apply highlighting
                    format = QTextCharFormat()
                    
                    # Set color based on selection
                    if color == 'yellow':
                        format.setBackground(QColor(255, 255, 0, 100))
                    elif color == 'green':
                        format.setBackground(QColor(0, 255, 0, 100))
                    elif color == 'blue':
                        format.setBackground(QColor(0, 191, 255, 100))
                    elif color == 'pink':
                        format.setBackground(QColor(255, 105, 180, 100))
                    elif color == 'orange':
                        format.setBackground(QColor(255, 165, 0, 100))
                    else:
                        format.setBackground(QColor(255, 255, 0, 100))
                        
                    cursor.mergeCharFormat(format)
                    self.text_edit.setTextCursor(cursor)
                    
                    # Process the highlight in the database
                    self._process_highlight_text(cursor.selectedText(), color)
                    
        except Exception as e:
            logger.exception(f"Error highlighting with color: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while highlighting: {str(e)}"
            )

    def _extract_from_context_menu(self):
        """Extract text from context menu selection and highlight it."""
        try:
            if not self.selected_text or len(self.selected_text.strip()) < 5:
                QMessageBox.warning(
                    self, "Extract", 
                    "Please select more text to extract."
                )
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
            
            # Get selected color
            color_name = self.highlight_color_combo.currentData()
            
            # Highlight the extracted text if in a web view
            if hasattr(self, 'web_view') and self.web_view:
                highlight_script = f"""
                (function() {{
                    if (typeof highlightExtractedText === 'function') {{
                        highlightExtractedText('{color_name}');
                        return true;
                    }}
                    return false;
                }})();
                """
                self.web_view.page().runJavaScript(highlight_script)
                
                # Also create a WebHighlight record for this extract
                from core.knowledge_base.models import WebHighlight
                
                highlight = WebHighlight(
                    document_id=self.document_id,
                    content=self.selected_text,
                    created_date=datetime.utcnow(),
                    color=color_name
                )
                
                # Save highlight
                self.db_session.add(highlight)
                self.db_session.commit()
            
            QMessageBox.information(
                self, "Extract", 
                "Extract created successfully. You can find it in the Knowledge Base."
            )
                
        except Exception as e:
            logger.exception(f"Error creating extract from context menu: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

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

    def _load_audio(self):
        """Load an audio file for playback with position tracking."""
        try:
            # First check if QtMultimedia is available
            if not QT_MULTIMEDIA_AVAILABLE:
                raise ImportError("PyQt6.QtMultimedia is not available. Audio playback requires this module to be properly installed.")
                
            from ui.load_audio_helper import setup_audio_player
            
            # Calculate initial position
            target_position = 0
            if hasattr(self.document, 'position') and self.document.position is not None:
                target_position = self.document.position
                
            # Set up the audio player
            self.audio_player = setup_audio_player(
                self, 
                self.document, 
                self.db_session, 
                target_position
            )
            
            # Add to layout
            self.content_layout.addWidget(self.audio_player)
            
            # Update last accessed timestamp
            self.document.last_accessed = datetime.now()
            self.db_session.commit()
            
        except (ImportError, RuntimeError) as e:
            logger.exception(f"Error loading audio file: {e}")
            error_label = QLabel(f"Error loading audio file: {str(e)}\n\nThis may be caused by an incompatible version of PyQt6-Multimedia.\nTry updating it with: pip install PyQt6-Multimedia==6.6.1 -U")
            error_label.setStyleSheet("color: red; padding: 10px;")
            error_label.setWordWrap(True)
            self.content_layout.addWidget(error_label)
            
            # Try to provide alternative playback options
            alt_label = QLabel("You can try opening this audio file with your system's default audio player:")
            alt_label.setStyleSheet("padding: 10px;")
            self.content_layout.addWidget(alt_label)
            
            # Add a button to open the file with the system's default player
            open_button = QPushButton("Open with System Player")
            open_button.clicked.connect(lambda: self._open_with_system_player())
            open_button.setMaximumWidth(200)
            self.content_layout.addWidget(open_button)
            
        except Exception as e:
            logger.exception(f"Unexpected error loading audio file: {e}")
            error_label = QLabel(f"Error loading audio file: {str(e)}")
            error_label.setStyleSheet("color: red;")
            self.content_layout.addWidget(error_label)
            
    def _open_with_system_player(self):
        """Open the audio file with the system's default player."""
        try:
            if not hasattr(self, 'document') or not hasattr(self.document, 'file_path'):
                return
                
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.document.file_path))
            
        except Exception as e:
            logger.exception(f"Error opening file with system player: {e}")
            QMessageBox.warning(self, "Error", f"Could not open the file with system player: {str(e)}")

    def _create_toolbar(self):
        """Create toolbar with common document actions."""
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(16, 16))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        
        # Navigation actions
        self.prev_button = QAction("Previous", self)
        self.prev_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft))
        self.prev_button.setStatusTip("Go to previous document")
        self.prev_button.triggered.connect(self._on_previous)
        toolbar.addAction(self.prev_button)
        
        self.next_button = QAction("Next", self)
        self.next_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        self.next_button.setStatusTip("Go to next document")
        self.next_button.triggered.connect(self._on_next)
        toolbar.addAction(self.next_button)
        
        toolbar.addSeparator()
        
        # Extract action
        self.extract_button = QAction("Extract", self)
        self.extract_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.extract_button.setStatusTip("Extract selected text")
        self.extract_button.triggered.connect(self._on_extract)
        toolbar.addAction(self.extract_button)
        
        # Highlight action
        self.highlight_button = QAction("Highlight", self)
        self.highlight_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        self.highlight_button.setStatusTip("Highlight selected text")
        self.highlight_button.triggered.connect(self._on_highlight)
        toolbar.addAction(self.highlight_button)
        
        # Color picker for highlighting
        self.highlight_color_combo = QComboBox()
        self.highlight_color_combo.addItem("Yellow", "yellow")
        self.highlight_color_combo.addItem("Green", "green")
        self.highlight_color_combo.addItem("Blue", "blue")
        self.highlight_color_combo.addItem("Pink", "pink")
        self.highlight_color_combo.addItem("Orange", "orange")
        self.highlight_color_combo.setCurrentIndex(0)
        self.highlight_color_combo.setToolTip("Select highlight color")
        self.highlight_color_combo.setStatusTip("Select highlight color")
        self.highlight_color_combo.setMaximumWidth(80)
        toolbar.addWidget(self.highlight_color_combo)
        
        toolbar.addSeparator()
        
        # Zoom actions
        self.zoom_out_button = QAction("Zoom Out", self)
        self.zoom_out_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekBackward))
        self.zoom_out_button.setStatusTip("Zoom out")
        self.zoom_out_button.triggered.connect(self._on_zoom_out)
        toolbar.addAction(self.zoom_out_button)
        
        self.zoom_in_button = QAction("Zoom In", self)
        self.zoom_in_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaSeekForward))
        self.zoom_in_button.setStatusTip("Zoom in")
        self.zoom_in_button.triggered.connect(self._on_zoom_in)
        toolbar.addAction(self.zoom_in_button)
        
        toolbar.addSeparator()
        
        # Incremental reading action
        self.ir_button = QAction("Add to IR", self)
        self.ir_button.setStatusTip("Add to incremental reading queue")
        self.ir_button.triggered.connect(self._on_add_to_incremental_reading)
        toolbar.addAction(self.ir_button)

        # Add Read Later button
        self.read_later_button = QAction("Read Later", self)
        self.read_later_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.read_later_button.setStatusTip("Save position for reading later")
        self.read_later_button.triggered.connect(self._on_add_read_later)
        toolbar.addAction(self.read_later_button)

        # Add bookmark button with dropdown menu
        bookmark_button = QToolButton()
        bookmark_button.setText("Bookmarks")
        bookmark_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        bookmark_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        bookmark_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

        # Create menu for bookmarks
        bookmark_menu = QMenu(bookmark_button)

        # Add action to show all bookmarks
        show_all_action = QAction("Show All Bookmarks", bookmark_button)
        show_all_action.triggered.connect(self._on_show_read_later_items)
        bookmark_menu.addAction(show_all_action)

        # Add separator
        bookmark_menu.addSeparator()

        # Set the menu to the button
        bookmark_button.setMenu(bookmark_menu)

        # Connect button click to show all bookmarks
        bookmark_button.clicked.connect(self._on_show_read_later_items)

        # Add to toolbar
        toolbar.addWidget(bookmark_button)
        self.bookmark_button = bookmark_button  # Save reference

        # Add reading stats button
        self.stats_button = QAction("Reading Stats", self)
        self.stats_button.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView))
        self.stats_button.setStatusTip("Show reading statistics")
        self.stats_button.triggered.connect(self._on_show_reading_stats)
        toolbar.addAction(self.stats_button)
            
        return toolbar

    def _on_previous(self):
        """Navigate to the previous document."""
        self.navigate.emit("previous")
    
    def _on_next(self):
        """Navigate to the next document."""
        self.navigate.emit("next")

    def _on_zoom_in(self):
        """Zoom in on the document content."""
        if hasattr(self, 'content_edit'):
            if isinstance(self.content_edit, QWebEngineView):
                # For web view, use zoom factor
                current_zoom = self.content_edit.zoomFactor()
                self.content_edit.setZoomFactor(current_zoom * 1.2)
            elif hasattr(self.content_edit, 'zoomIn'):
                # For text edit, use zoom in method
                self.content_edit.zoomIn(2)
    
    def _on_zoom_out(self):
        """Zoom out on the document content."""
        if hasattr(self, 'content_edit'):
            if isinstance(self.content_edit, QWebEngineView):
                # For web view, use zoom factor
                current_zoom = self.content_edit.zoomFactor()
                self.content_edit.setZoomFactor(current_zoom / 1.2)
            elif hasattr(self.content_edit, 'zoomOut'):
                # For text edit, use zoom out method
                self.content_edit.zoomOut(2)

    def _on_add_to_incremental_reading(self):
        """Add the current document to the incremental reading queue."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            # Use the IR manager to add document to queue
            ir_manager = IncrementalReadingManager(self.db_session)
            ir_manager.add_document_to_queue(self.document_id)
            
            QMessageBox.information(
                self, "Incremental Reading", 
                "Document added to incremental reading queue."
            )
                
        except Exception as e:
            logger.exception(f"Error adding to incremental reading: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _on_highlight(self):
        """Highlight the selected text in the document."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            # Get the selected highlight color
            color_name = self.highlight_color_combo.currentData()
            
            # Get selected text
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, use JavaScript to get selected text and apply highlight
                script = f"""
                (function() {{
                    var selection = window.getSelection();
                    var text = selection.toString();
                    if (text && text.trim().length > 0) {{
                        // Apply highlight
                        if (typeof highlightExtractedText === 'function') {{
                            // Create highlight span
                            var sel = window.getSelection();
                            if (sel.rangeCount > 0) {{
                                var range = sel.getRangeAt(0);
                                
                                // Create highlight span
                                var highlightSpan = document.createElement('span');
                                highlightSpan.className = 'incrementum-highlight';
                                
                                // Set color based on selection
                                switch('{color_name}') {{
                                    case 'yellow':
                                        highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                        break;
                                    case 'green':
                                        highlightSpan.style.backgroundColor = 'rgba(0, 255, 0, 0.3)';
                                        break;
                                    case 'blue':
                                        highlightSpan.style.backgroundColor = 'rgba(0, 191, 255, 0.3)';
                                        break;
                                    case 'pink':
                                        highlightSpan.style.backgroundColor = 'rgba(255, 105, 180, 0.3)';
                                        break;
                                    case 'orange':
                                        highlightSpan.style.backgroundColor = 'rgba(255, 165, 0, 0.3)';
                                        break;
                                    default:
                                        highlightSpan.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                }}
                                
                                highlightSpan.style.borderRadius = '2px';
                                
                                try {{
                                    // Apply highlight
                                    range.surroundContents(highlightSpan);
                                    
                                    // Clear selection
                                    sel.removeAllRanges();
                                }} catch (e) {{
                                    console.error('Error highlighting text:', e);
                                }}
                            }}
                        }}
                        return text;
                    }}
                    return '';
                }})();
                """
                self.web_view.page().runJavaScript(
                    script,
                    lambda result: self._process_highlight_text(result, color_name)
                )
                return
            elif hasattr(self, 'text_edit') and self.text_edit:
                # For text edit, get selection and apply highlight
                cursor = self.text_edit.textCursor()
                selected_text = cursor.selectedText()
                if selected_text:
                    # Apply highlighting to the selection
                    format = QTextCharFormat()
                    
                    # Set color based on selection
                    if color_name == 'yellow':
                        format.setBackground(QColor(255, 255, 0, 100))
                    elif color_name == 'green':
                        format.setBackground(QColor(0, 255, 0, 100))
                    elif color_name == 'blue':
                        format.setBackground(QColor(0, 191, 255, 100))
                    elif color_name == 'pink':
                        format.setBackground(QColor(255, 105, 180, 100))
                    elif color_name == 'orange':
                        format.setBackground(QColor(255, 165, 0, 100))
                    else:
                        format.setBackground(QColor(255, 255, 0, 100))
                        
                    cursor.mergeCharFormat(format)
                    self.text_edit.setTextCursor(cursor)
                    self._process_highlight_text(selected_text, color_name)
                else:
                    QMessageBox.warning(
                        self, "Highlight", 
                        "Please select some text to highlight."
                    )
                    
        except Exception as e:
            logger.exception(f"Error creating highlight: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _process_highlight_text(self, selected_text, color_name='yellow'):
        """Process text after highlighting from web view or text edit."""
        try:
            if not selected_text or len(selected_text.strip()) < 5:
                QMessageBox.warning(
                    self, "Highlight", 
                    "Please select more text to highlight (at least 5 characters)."
                )
                return
                
            # Create web highlight record
            from core.knowledge_base.models import WebHighlight
            
            highlight = WebHighlight(
                document_id=self.document_id,
                content=selected_text,
                created_date=datetime.utcnow(),
                color=color_name
            )
            
            # Save highlight
            self.db_session.add(highlight)
            self.db_session.commit()
            
            QMessageBox.information(
                self, "Highlight", 
                f"Text highlighted successfully with {color_name} color."
            )
                
        except Exception as e:
            logger.exception(f"Error creating highlight: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _on_mark_reading_progress(self):
        """Mark the reading progress for the current document."""
        try:
            if not hasattr(self, 'document_id') or not self.document_id:
                logger.warning("No document loaded")
                return
                
            document = self.db_session.query(Document).get(self.document_id)
            if not document:
                logger.warning(f"Document not found: {self.document_id}")
                return
            
            # Get current position
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, get scroll position using JavaScript
                self.web_view.page().runJavaScript(
                    "window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;",
                    lambda result: self._save_position_to_document(result)
                )
                return  # We'll continue in the callback
            elif hasattr(self, 'content_edit') and hasattr(self.content_edit, 'verticalScrollBar'):
                # For text edit or other scrollable widgets
                scrollbar = self.content_edit.verticalScrollBar()
                position = scrollbar.value()
                self._save_position_to_document(position)
            else:
                QMessageBox.warning(
                    self, "Reading Progress", 
                    "Unable to determine reading position for this document type."
                )
                
        except Exception as e:
            logger.exception(f"Error marking reading progress: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _save_position_to_document(self, position):
        """Save the position to the document."""
        try:
            document = self.db_session.query(Document).get(self.document_id)
            if document:
                # Update document position directly
                document.position = position
                document.last_accessed = datetime.utcnow()
                self.db_session.commit()
                
                QMessageBox.information(
                    self, "Reading Progress", 
                    "Reading position saved. You can continue from this point next time."
                )
                
                logger.debug(f"Saved position {position} for document {self.document_id}")
            else:
                logger.warning(f"Document not found: {self.document_id}")
                QMessageBox.warning(
                    self, "Reading Progress", 
                    "Document not found. Unable to save position."
                )
        except Exception as e:
            logger.exception(f"Error saving reading position: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )

    def _on_extract_selected(self, extract_id):
        """Handle when an extract is selected in the extract view.
        
        Args:
            extract_id (int): ID of the selected extract
        """
        try:
            # Get the extract from the database
            extract = self.db_session.query(Extract).get(extract_id)
            
            if not extract:
                logger.warning(f"Extract not found: {extract_id}")
                return
                
            # Highlight the extract text in the document if possible
            if hasattr(self, 'web_view') and self.web_view:
                # For web view, find and highlight the text
                script = f"""
                (function() {{
                    const text = {json.dumps(extract.content)};
                    if (!text) return false;
                    
                    const selection = window.getSelection();
                    const range = document.createRange();
                    const allTextNodes = [];
                    
                    // Get all text nodes
                    function getTextNodes(node) {{
                        if (node.nodeType === 3) {{
                            allTextNodes.push(node);
                        }} else {{
                            for (let i = 0; i < node.childNodes.length; i++) {{
                                getTextNodes(node.childNodes[i]);
                            }}
                        }}
                    }}
                    
                    getTextNodes(document.body);
                    
                    // Find the text in the document
                    for (let i = 0; i < allTextNodes.length; i++) {{
                        const nodeText = allTextNodes[i].textContent;
                        const index = nodeText.indexOf(text);
                        if (index >= 0) {{
                            // Found the text
                            range.setStart(allTextNodes[i], index);
                            range.setEnd(allTextNodes[i], index + text.length);
                            selection.removeAllRanges();
                            selection.addRange(range);
                            
                            // Scroll to the text
                            const rect = range.getBoundingClientRect();
                            window.scrollTo({{
                                top: window.scrollY + rect.top - 100,
                                behavior: 'smooth'
                            }});
                            
                            return true;
                        }}
                    }}
                    
                    return false;
                }})();
                """
                self.web_view.page().runJavaScript(script)
            elif hasattr(self, 'content_edit') and isinstance(self.content_edit, QTextEdit):
                # For text edit, find and highlight the text
                cursor = self.content_edit.textCursor()
                cursor.setPosition(0)
                self.content_edit.setTextCursor(cursor)
                
                if self.content_edit.find(extract.content):
                    # Text found, it's now selected
                    # Ensure visible
                    self.content_edit.ensureCursorVisible()
                else:
                    logger.warning(f"Could not find extract text in document: {extract.content[:50]}...")
            
            logger.debug(f"Selected extract: {extract_id}")
            
        except Exception as e:
            logger.exception(f"Error selecting extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while selecting the extract: {str(e)}"
            )

