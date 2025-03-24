import os
import logging
from datetime import datetime
from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolBar, 
    QLineEdit, QPushButton, QSplitter, QMessageBox,
    QStatusBar, QProgressBar, QMenu, QLabel, QSizePolicy,
    QApplication, QFileDialog
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
    
    def __init__(self, db_session, parent=None):
        super().__init__(parent)
        
        if not HAS_WEBENGINE:
            raise ImportError("Web browsing requires QWebEngineView")
        
        self.db_session = db_session
        self.selected_text = ""
        self._current_url = ""
        self.current_title = "New Tab"
        self.cached_content = ""
        self.current_document_id = None
        
        # Create the UI
        self._create_ui()
        
        # Load default page
        self.navigate_to("about:blank")
    
    @property
    def current_url(self):
        """Get the current URL of the web browser."""
        if hasattr(self, 'web_view') and self.web_view:
            return self.web_view.url().toString()
        return self._current_url
    
    def load_url(self, url):
        """Load the specified URL in the web browser."""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        self._current_url = url
        self.url_bar.setText(url)
        self.web_view.load(QUrl(url))
    
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
        self._current_url = url_str
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
                position=f"url:{self._current_url},{extract_data['position']}",
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
        """Save the current page as a self-contained HTML document with all resources embedded."""
        try:
            # Show status
            self.status_label.setText("Preparing to save page...")
            
            # Inject script to serialize the page with all resources embedded
            serialize_script = """
            (function() {
                // Helper function to convert URLs to data URLs
                async function resourceToDataURL(resourceURL, resourceType) {
                    try {
                        // Handle relative URLs
                        const absoluteURL = new URL(resourceURL, document.baseURI).href;
                        const response = await fetch(absoluteURL, { cache: 'force-cache' });
                        if (!response.ok) return null;
                        
                        const blob = await response.blob();
                        return new Promise((resolve) => {
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        });
                    } catch (error) {
                        console.error('Error processing resource', resourceURL, error);
                        return null;
                    }
                }
                
                // Process all images
                async function processImages() {
                    const images = document.querySelectorAll('img');
                    for (const img of images) {
                        if (img.src && !img.src.startsWith('data:')) {
                            const dataURL = await resourceToDataURL(img.src, 'image');
                            if (dataURL) img.src = dataURL;
                        }
                        // Also check srcset attribute
                        if (img.srcset) {
                            img.removeAttribute('srcset');
                        }
                    }
                }
                
                // Process all CSS
                async function processCSS() {
                    const styles = document.querySelectorAll('link[rel="stylesheet"]');
                    for (const style of styles) {
                        try {
                            if (style.href) {
                                const response = await fetch(style.href);
                                if (response.ok) {
                                    const cssText = await response.text();
                                    // Create a new style element
                                    const inlineStyle = document.createElement('style');
                                    inlineStyle.textContent = cssText;
                                    // Replace the link with the inline style
                                    style.parentNode.replaceChild(inlineStyle, style);
                                }
                            }
                        } catch (error) {
                            console.error('Error processing CSS', style.href, error);
                        }
                    }
                    
                    // Process inline styles with background-image
                    const elementsWithStyle = document.querySelectorAll('[style*="background"]');
                    for (const el of elementsWithStyle) {
                        const style = getComputedStyle(el);
                        if (style.backgroundImage && style.backgroundImage !== 'none' && !style.backgroundImage.startsWith('data:')) {
                            try {
                                // Extract URL from background-image
                                const urlMatch = /url\\(['"](.*?)['"]*\\)/g.exec(style.backgroundImage);
                                if (urlMatch && urlMatch[1]) {
                                    const dataURL = await resourceToDataURL(urlMatch[1], 'image');
                                    if (dataURL) {
                                        // Update style attribute with data URL
                                        const newBgImage = `background-image: url(${dataURL})`;
                                        const currentStyle = el.getAttribute('style') || '';
                                        const newStyle = currentStyle.replace(/background-image:[^;]+;?/g, '') + newBgImage;
                                        el.setAttribute('style', newStyle);
                                    }
                                }
                            } catch (error) {
                                console.error('Error processing background image', error);
                            }
                        }
                    }
                }
                
                // Process all scripts
                async function processScripts() {
                    const scripts = document.querySelectorAll('script[src]');
                    for (const script of scripts) {
                        try {
                            if (script.src) {
                                const response = await fetch(script.src);
                                if (response.ok) {
                                    const jsText = await response.text();
                                    // Create a new script element
                                    const inlineScript = document.createElement('script');
                                    inlineScript.textContent = jsText;
                                    // Copy any attributes except src
                                    for (const attr of script.attributes) {
                                        if (attr.name !== 'src') {
                                            inlineScript.setAttribute(attr.name, attr.value);
                                        }
                                    }
                                    // Replace the original script
                                    script.parentNode.replaceChild(inlineScript, script);
                                }
                            }
                        } catch (error) {
                            console.error('Error processing script', script.src, error);
                        }
                    }
                }
                
                // Process fonts and other resources
                async function processFonts() {
                    // Handle CSS @font-face rules and other external resources
                    // This is a simplified approach
                    const styleSheets = document.styleSheets;
                    for (const sheet of styleSheets) {
                        try {
                            // Skip if it's a CSSStyleSheet we can't access (e.g., cross-origin)
                            if (!sheet.cssRules) continue;
                            
                            for (let i = 0; i < sheet.cssRules.length; i++) {
                                const rule = sheet.cssRules[i];
                                // Handle @import rules
                                if (rule.type === CSSRule.IMPORT_RULE && rule.href) {
                                    try {
                                        const response = await fetch(rule.href);
                                        if (response.ok) {
                                            const cssText = await response.text();
                                            // Create a style element with this CSS
                                            const style = document.createElement('style');
                                            style.textContent = cssText;
                                            document.head.appendChild(style);
                                        }
                                    } catch (error) {
                                        console.error('Error processing @import', rule.href, error);
                                    }
                                }
                            }
                        } catch (error) {
                            // Security error, probably cross-origin stylesheet
                            console.error('Error processing stylesheet', error);
                        }
                    }
                }
                
                // Add meta tags for standalone operation
                function addMetaTags() {
                    // Add charset meta tag if not exists
                    if (!document.querySelector('meta[charset]')) {
                        const meta = document.createElement('meta');
                        meta.setAttribute('charset', 'UTF-8');
                        document.head.insertBefore(meta, document.head.firstChild);
                    }
                    
                    // Add viewport meta tag if not exists
                    if (!document.querySelector('meta[name="viewport"]')) {
                        const meta = document.createElement('meta');
                        meta.setAttribute('name', 'viewport');
                        meta.setAttribute('content', 'width=device-width, initial-scale=1.0');
                        document.head.appendChild(meta);
                    }
                    
                    // Add info comment
                    const infoComment = document.createComment(
                        ' Saved with Incrementum ' + 
                        new Date().toISOString() + 
                        ' from ' + window.location.href + ' '
                    );
                    document.documentElement.insertBefore(infoComment, document.documentElement.firstChild);
                }
                
                // Main function to process everything
                async function processPage() {
                    addMetaTags();
                    
                    // Process all resources in parallel
                    await Promise.all([
                        processImages(),
                        processCSS(),
                        processScripts(),
                        processFonts()
                    ]);
                    
                    // Get the processed HTML
                    return {
                        title: document.title,
                        html: '<!DOCTYPE html>\\n' + document.documentElement.outerHTML
                    };
                }
                
                // Execute and return the result
                return processPage();
            })();
            """
            
            # Execute the script to embed all resources
            self.status_label.setText("Embedding all resources (this may take a moment)...")
            self.web_view.page().runJavaScript(serialize_script, self._save_self_contained_page)
            
        except Exception as e:
            logger.exception(f"Error preparing page for saving: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to prepare page for saving: {str(e)}"
            )

    def _save_self_contained_page(self, result):
        """Save the self-contained HTML page with all embedded resources."""
        try:
            if not result:
                self.status_label.setText("Failed to process page")
                QMessageBox.warning(
                    self, "Error", 
                    "Failed to process page resources"
                )
                return
                
            import os
            import re
            from datetime import datetime
                
            # Get page title and sanitize for filename
            page_title = result.get('title', 'Untitled Page')
            html_content = result.get('html', '')
            
            # Sanitize title for use as filename
            safe_title = re.sub(r'[^\w\-_\. ]', '_', page_title)
            safe_title = safe_title.strip()[:50]  # Limit length
            
            # Create timestamp for unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_title}_{timestamp}.html"
            
            # Ask user for save location
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Save Complete Web Page",
                filename,
                "HTML Files (*.html);;All Files (*.*)"
            )
            
            if not save_path:
                self.status_label.setText("Save cancelled")
                return
            
            # Save the HTML content to the file
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Create document in the database
            document = Document(
                title=page_title[:100],
                file_path=save_path,
                content_type="html",
                author="Web",
                source_url=self._current_url,
                imported_date=datetime.utcnow(),
                last_accessed=datetime.utcnow()
            )
            
            # Add to database
            self.db_session.add(document)
            self.db_session.commit()
            
            # Store the document ID
            self.current_document_id = document.id
            
            # Show success message
            self.status_label.setText(f"Page saved to {save_path}")
            QMessageBox.information(
                self, "Page Saved", 
                f"The web page has been saved with all resources embedded as:\n{save_path}"
            )
            
        except Exception as e:
            logger.exception(f"Error saving self-contained page: {e}")
            self.status_label.setText("Error saving page")
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
                source_url=self._current_url,
                imported_date=datetime.utcnow(),
                last_accessed=datetime.utcnow()
            )
            
            # Add to database
            self.db_session.add(document)
            self.db_session.commit()
            
            # Store document ID
            document_id = document.id
            self.current_document_id = document_id
            
            logger.info(f"Created document for web page directly: {self._current_url}")
            
            # If we have pending extract creation, process it now
            if hasattr(self, 'pending_extract_data') and self.pending_extract_data:
                self._create_extract_with_data(self.pending_extract_data)
                self.pending_extract_data = None
            
            return document_id
            
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
        url_obj = urlparse(self._current_url)
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