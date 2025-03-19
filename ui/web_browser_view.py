import os
import logging
from datetime import datetime
from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, 
    QLineEdit, QPushButton, QSplitter, QMessageBox,
    QStatusBar, QProgressBar, QMenu, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, pyqtSlot, QObject
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebChannel import QWebChannel
    HAS_WEBENGINE = True
except ImportError:
    HAS_WEBENGINE = False
from PyQt6.QtGui import QIcon, QKeySequence, QAction

from core.knowledge_base.models import Document, Extract

logger = logging.getLogger(__name__)

class WebViewCallback(QObject):
    """Class to handle callbacks from JavaScript in QWebEngineView."""
    
    def __init__(self, browser_view):
        super().__init__()
        self.browser_view = browser_view
    
    @pyqtSlot(str)
    def selectionChanged(self, text):
        """Handle selection change from JavaScript."""
        self.browser_view.selected_text = text

class WebBrowserView(QWidget):
    """Web browser component for browsing websites and creating extracts."""
    
    extractCreated = pyqtSignal(int)  # extract_id
    
    def __init__(self, db_session):
        super().__init__()
        
        if not HAS_WEBENGINE:
            raise ImportError("Web browsing requires QWebEngineView")
        
        self.db_session = db_session
        self.selected_text = ""
        self.current_url = ""
        self.current_title = "New Tab"
        self.cached_content = ""
        self.current_document_id = None
        
        # Create the UI
        self._create_ui()
        
        # Load default page
        self.navigate_to("about:blank")
    
    def _create_ui(self):
        """Create the UI components."""
        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Navigation toolbar
        nav_toolbar = QToolBar()
        
        # Back and forward buttons
        self.back_button = QPushButton("←")
        self.back_button.setToolTip("Go Back")
        self.back_button.clicked.connect(self._on_back)
        nav_toolbar.addWidget(self.back_button)
        
        self.forward_button = QPushButton("→")
        self.forward_button.setToolTip("Go Forward")
        self.forward_button.clicked.connect(self._on_forward)
        nav_toolbar.addWidget(self.forward_button)
        
        # Reload button
        self.reload_button = QPushButton("↻")
        self.reload_button.setToolTip("Reload")
        self.reload_button.clicked.connect(self._on_reload)
        nav_toolbar.addWidget(self.reload_button)
        
        # URL bar
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL...")
        self.url_bar.returnPressed.connect(self._on_url_changed)
        nav_toolbar.addWidget(self.url_bar)
        
        # Go button
        self.go_button = QPushButton("Go")
        self.go_button.clicked.connect(self._on_url_changed)
        nav_toolbar.addWidget(self.go_button)
        
        # Extract button
        self.extract_button = QPushButton("Create Extract")
        self.extract_button.setEnabled(False)
        self.extract_button.clicked.connect(self._on_create_extract)
        nav_toolbar.addWidget(self.extract_button)
        
        # Save page button
        self.save_button = QPushButton("Save Page")
        self.save_button.clicked.connect(self._on_save_page)
        nav_toolbar.addWidget(self.save_button)
        
        layout.addWidget(nav_toolbar)
        
        # Create a main container with web view and status bar
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Web view
        self.web_view = QWebEngineView()
        self.web_view.loadStarted.connect(self._on_load_started)
        self.web_view.loadProgress.connect(self._on_load_progress)
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.titleChanged.connect(self._on_title_changed)
        self.web_view.urlChanged.connect(self._on_url_updated)
        
        # Set up JavaScript communication
        channel = QWebChannel(self.web_view.page())
        self.callback_handler = WebViewCallback(self)
        channel.registerObject("callbackHandler", self.callback_handler)
        self.web_view.page().setWebChannel(channel)
        
        # Set up context menu
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.web_view.customContextMenuRequested.connect(self._on_context_menu)
        
        # Set size policy to expand
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        main_layout.addWidget(self.web_view, 1)  # Give web view a stretch factor of 1
        
        # Status bar
        self.status_bar = QStatusBar()
        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(100)
        self.progress_bar.setMaximumHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        main_layout.addWidget(self.status_bar)
        
        # Add the main container to the layout with stretch
        layout.addWidget(main_container, 1)  # Give main container a stretch factor of 1
        
        self.setLayout(layout)
        
        # Inject selection tracking JavaScript
        self._inject_selection_tracking()
    
    def _inject_selection_tracking(self):
        """Inject JavaScript to track text selection."""
        selection_js = """
        document.addEventListener('selectionchange', function() {
            const selection = window.getSelection();
            const text = selection.toString();
            if (text && text.trim().length > 0 && typeof callbackHandler !== 'undefined') {
                callbackHandler.selectionChanged(text);
            }
        });
        
        // Store this for later in case WebChannel isn't ready
        document.addEventListener('mouseup', function() {
            const selection = window.getSelection();
            const text = selection.toString();
            if (text && text.trim().length > 0) {
                window.lastSelection = text;
            }
        });
        """
        
        # Set up to inject after page loads
        self.web_view.loadFinished.connect(
            lambda ok: self.web_view.page().runJavaScript(selection_js)
        )
    
    def navigate_to(self, url):
        """Navigate to the specified URL."""
        if not url.startswith(('http://', 'https://', 'file://', 'about:')):
            url = 'https://' + url
        
        self.web_view.load(QUrl(url))
        self.url_bar.setText(url)
    
    def _get_selection(self):
        """Get the current selection from the web view."""
        self.web_view.page().runJavaScript(
            "window.getSelection().toString() || window.lastSelection || '';",
            self._on_selection_result
        )
    
    def _on_selection_result(self, text):
        """Handle selection result."""
        if text and text.strip():
            self.selected_text = text.strip()
            self.extract_button.setEnabled(True)
        else:
            self.selected_text = ""
            self.extract_button.setEnabled(False)
    
    def _on_url_changed(self):
        """Handle URL bar change."""
        url = self.url_bar.text()
        self.navigate_to(url)
    
    def _on_back(self):
        """Navigate back."""
        self.web_view.back()
    
    def _on_forward(self):
        """Navigate forward."""
        self.web_view.forward()
    
    def _on_reload(self):
        """Reload the current page."""
        self.web_view.reload()
    
    def _on_load_started(self):
        """Handle load started event."""
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.status_label.setText("Loading...")
        
        # Reset selection
        self.selected_text = ""
        self.extract_button.setEnabled(False)
        
        # Reset page content
        self.cached_content = ""
    
    def _on_load_progress(self, progress):
        """Handle load progress event."""
        self.progress_bar.setValue(progress)
    
    def _on_load_finished(self, success):
        """Handle load finished event."""
        self.progress_bar.hide()
        
        if success:
            self.status_label.setText("Page loaded")
            
            # Cache page content for extracts
            self._cache_page_content()
        else:
            self.status_label.setText("Failed to load page")
    
    def _on_title_changed(self, title):
        """Handle title changed event."""
        self.current_title = title if title else "Untitled"
    
    def _on_url_updated(self, url):
        """Handle URL changed event."""
        url_str = url.toString()
        self.current_url = url_str
        self.url_bar.setText(url_str)
        
        # Update back/forward buttons
        self.back_button.setEnabled(self.web_view.history().canGoBack())
        self.forward_button.setEnabled(self.web_view.history().canGoForward())
    
    def _cache_page_content(self):
        """Cache the page content for extract context."""
        self.web_view.page().runJavaScript(
            "document.body.innerText;",
            self._on_page_content_result
        )
    
    def _on_page_content_result(self, content):
        """Handle page content result."""
        if content:
            self.cached_content = content
    
    def _on_context_menu(self, pos):
        """Show context menu."""
        # Get current selection
        self._get_selection()
        
        # Create menu
        menu = QMenu(self)
        
        # Add extract action if text is selected
        if self.selected_text:
            extract_action = menu.addAction("Create Extract")
            extract_action.triggered.connect(self._on_create_extract)
        
        # Add page actions
        menu.addSeparator()
        save_page_action = menu.addAction("Save Page")
        save_page_action.triggered.connect(self._on_save_page)
        
        # Show menu
        menu.exec(self.web_view.mapToGlobal(pos))
    
    def _on_create_extract(self):
        """Create extract from selected text."""
        if not self.selected_text:
            self._get_selection()
            if not self.selected_text:
                QMessageBox.information(
                    self, "No Selection", 
                    "Please select some text to create an extract."
                )
                return
        
        try:
            # Get context for the extract (surrounding text)
            if self.cached_content:
                # Find the selection in the content to get proper context
                selection_index = self.cached_content.find(self.selected_text)
                if selection_index >= 0:
                    # Get surrounding context
                    start_pos = max(0, selection_index - 100)
                    end_pos = min(len(self.cached_content), selection_index + len(self.selected_text) + 100)
                    context = self.cached_content[start_pos:end_pos]
                    position = f"pos:{selection_index}"
                else:
                    # Fallback if we can't find the exact text
                    context = self.selected_text
                    position = "unknown"
            else:
                context = self.selected_text
                position = "unknown"
            
            # Prepare extract data
            extract_data = {
                'content': self.selected_text,
                'context': context,
                'position': position,
            }
            
            # Make sure we have a document to associate with
            if not self.current_document_id:
                # We need to create the document first and then create the extract
                self.status_label.setText("Creating document before extract...")
                
                # Store the extract data for later
                self.pending_extract_data = extract_data
                
                # Start document creation
                self._ensure_document_exists()
                
                # UI feedback
                QMessageBox.information(
                    self, "Document Creation", 
                    "Creating document first... Your extract will be created automatically when done."
                )
                return
                
            # If we already have a document ID, create the extract now
            self._create_extract_with_data(extract_data)
            
        except Exception as e:
            logger.exception(f"Error preparing extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to prepare extract: {str(e)}"
            )
    
    def _create_extract_with_data(self, extract_data):
        """Create extract from prepared data."""
        try:
            # Create the extract
            extract = Extract(
                content=extract_data['content'],
                context=extract_data['context'],
                document_id=self.current_document_id,
                position=f"url:{self.current_url},{extract_data['position']}",
                created_date=datetime.utcnow()
            )
            
            # Add to database
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Emit signal
            self.extractCreated.emit(extract.id)
            
            # Show confirmation
            self.status_label.setText(f"Extract created: {extract_data['content'][:30]}...")
            
            # Clear selection
            self.selected_text = ""
            self.extract_button.setEnabled(False)
            
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to create extract: {str(e)}"
            )
    
    def _on_save_page(self):
        """Save the current page as a document."""
        try:
            self._ensure_document_exists(force_new=True)
            QMessageBox.information(
                self, "Page Saved", 
                f"The page '{self.current_title}' has been saved as a document."
            )
        except Exception as e:
            logger.exception(f"Error saving page: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to save page: {str(e)}"
            )
    
    def _create_document(self, html_content, filename):
        """Create a document with the HTML content."""
        try:
            # Create document directory if needed
            import tempfile
            import os
            
            # Create a temporary file to store the HTML
            fd, file_path = tempfile.mkstemp(suffix=f"_{filename}")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Create document - note the field is "imported_date" not "import_date"
            document = Document(
                title=self.current_title[:100],
                file_path=file_path,
                content_type="html",
                author="Web",
                source_url=self.current_url,
                imported_date=datetime.utcnow(),
                last_accessed=datetime.utcnow()
            )
            
            # Add to database
            self.db_session.add(document)
            self.db_session.commit()
            
            # Store document ID
            self.current_document_id = document.id
            
            logger.info(f"Created document for web page: {self.current_url}")
            
            # If we have pending extract creation, process it now
            if hasattr(self, 'pending_extract_data') and self.pending_extract_data:
                self._create_extract_with_data(self.pending_extract_data)
                self.pending_extract_data = None
            
            return document.id
            
        except Exception as e:
            logger.exception(f"Error creating document: {e}")
            
            # If extract creation was pending, show error
            if hasattr(self, 'pending_extract_data') and self.pending_extract_data:
                QMessageBox.warning(
                    self, "Extract Creation Failed", 
                    f"Failed to create document for extract: {str(e)}"
                )
                self.pending_extract_data = None
            
            raise

    def _ensure_document_exists(self, force_new=False):
        """Ensure a document exists for the current page."""
        if self.current_document_id is not None and not force_new:
            # Document already exists
            return self.current_document_id
        
        # Parse the URL to create a valid filename
        url_obj = urlparse(self.current_url)
        hostname = url_obj.netloc
        path = url_obj.path.replace('/', '_')
        
        # Create a filename based on the URL
        filename = f"{hostname}{path}"
        if not filename or filename == "about_blank":
            filename = "webpage"
        
        # Add date to make it unique
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename}_{date_str}.html"
        
        # For extract creation, we need the document ID right away
        # Use asynchronous method since we can't get HTML content synchronously
        self.web_view.page().runJavaScript(
            "document.documentElement.outerHTML;",
            lambda html: self._create_document(html, filename)
        )
        
        # Return None to indicate document is being created asynchronously
        return None 