# ui/main_window.py - Fully integrated with all components

import os
import sys
import logging
import json
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import func

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QToolBar, QToolButton,
    QStatusBar, QMenuBar, QMenu, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QWidget, QDialog,
    QMessageBox, QFileDialog, QApplication,
    QDockWidget, QScrollArea, QSplitter, QTreeView,
    QListView, QSizePolicy, QStyle, QComboBox,
    QLineEdit, QCompleter, QDialogButtonBox, QFrame,
    QInputDialog, QProgressBar, QListWidget, QTextEdit,
    QGroupBox, QProgressDialog
)
from PyQt6.QtCore import Qt, QSize, QModelIndex, pyqtSignal, pyqtSlot, QTimer, QPoint, QThread, QByteArray, QUrl
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap, QAction, QActionGroup

from core.knowledge_base.models import init_database, Document, Category, Extract, LearningItem, Tag, YouTubePlaylistVideo
from core.document_processor.processor import DocumentProcessor
from core.spaced_repetition import FSRSAlgorithm
from core.content_extractor.nlp_extractor import NLPExtractor
from core.knowledge_base.search_engine import SearchEngine
from core.knowledge_base.tag_manager import TagManager
from core.knowledge_base.export_manager import ExportManager
from core.knowledge_network.network_builder import KnowledgeNetworkBuilder
from core.utils.settings_manager import SettingsManager
from core.utils.theme_manager import ThemeManager
from core.utils.rss_feed_manager import RSSFeedManager
from core.spaced_repetition.queue_manager import QueueManager
from core.content_extractor.extract_processor import ExtractProcessor
from core.learning.item_generator import LearningItemGenerator

from .document_view import DocumentView
from .pdf_view import PDFViewWidget
from .extract_view import ExtractView
from .review_view import ReviewView
from .statistics_view import StatisticsWidget
from .search_view import SearchView
from .tag_view import TagView
from .network_view import NetworkView
from .settings_dialog import SettingsDialog
from .backup_view import BackupView
from .export_dialog import ExportDialog
from .import_dialog import ImportDialog
from .learning_item_editor import LearningItemEditor
from .models.document_model import DocumentModel
from .models.category_model import CategoryModel
from .web_browser_view import WebBrowserView
from .sync_view import SyncView
from core.utils.shortcuts import ShortcutManager
from .arxiv_dialog import ArxivDialog
from core.document_processor.summarizer import SummarizeDialog
from .queue_view import QueueView
from ui.dialogs.url_import_dialog import URLImportDialog
from ui.dialogs.content_processor_dialog import ContentProcessorDialog
from ui.dialogs.rss_feed_dialog import RSSFeedDialog
from .rss_view import RSSView
from .incremental_reading_view import IncrementalReadingView
from .detailed_queue_view import DetailedQueueView
from .youtube_playlist_view import YouTubePlaylistView

logger = logging.getLogger(__name__)

class DockablePDFView(QDockWidget):
    """Dockable widget containing a PDF viewer."""
    
    extractCreated = pyqtSignal(int)
    navigate = pyqtSignal(str)  # Add navigation signal
    
    def __init__(self, document, db_session, parent=None):
        """Initialize the dockable PDF view.
        
        Args:
            document: Document object
            db_session: Database session
            parent: Parent widget
        """
        super().__init__(parent)
        self.document = document
        self.db_session = db_session
        
        # Set up the widget
        self.setWindowTitle(f"Document: {document.title}")
        self.setObjectName(f"pdf_view_{document.id}")
        
        # Create central widget
        self.central_widget = QWidget()
        self.setWidget(self.central_widget)
        
        # Create layout
        self.layout = QVBoxLayout(self.central_widget)
        
        # Create content viewer based on document type
        if document.content_type == 'youtube':
            # Create YouTube player
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings
            self.web_view = QWebEngineView()
            
            # Configure web settings
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowGeolocationOnInsecureOrigins, True)
            
            # Get video ID from URL
            from ui.load_youtube_helper import setup_youtube_webview, extract_video_id_from_document
            video_id = extract_video_id_from_document(document)
            
            if video_id:
                # Get target position from document, default to 0 if None
                target_position = getattr(document, 'position', 0) or 0
                
                # Create simple HTML with direct iframe
                html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1">
                    <style>
                        body {{ margin: 0; padding: 0; height: 100vh; overflow: hidden; }}
                        .video-container {{ width: 100%; height: 100%; }}
                        iframe {{ width: 100%; height: 100%; border: none; }}
                    </style>
                    <script>
                        // Ensure target_position is a valid number
                        const startPosition = {target_position};
                        const validStartPosition = isNaN(startPosition) ? 0 : Math.max(0, startPosition);
                    </script>
                </head>
                <body>
                    <div class="video-container">
                        <iframe 
                            src="https://www.youtube.com/embed/{video_id}?autoplay=1&start={{validStartPosition}}&enablejsapi=1&origin=https://www.youtube.com" 
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowfullscreen>
                        </iframe>
                    </div>
                </body>
                </html>
                """
                
                # Load the HTML content
                from PyQt6.QtCore import QUrl
                self.web_view.setHtml(html, QUrl("https://www.youtube.com/"))
                self.layout.addWidget(self.web_view)
            else:
                QMessageBox.warning(self, "Error", "Could not extract video ID from URL")
                return
                
        else:
            # Create PDF viewer
            self.pdf_view = PDFViewer(document, db_session)
            self.layout.addWidget(self.pdf_view)
            
            # Connect signals
            self.pdf_view.extractCreated.connect(self.extractCreated.emit)
            self.pdf_view.navigate.connect(self.navigate.emit)
            
        # Set up close button
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.layout.addWidget(self.close_button)
        
        # Set up floating and allowed areas
        self.setFloating(True)
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea |
            Qt.DockWidgetArea.RightDockWidgetArea |
            Qt.DockWidgetArea.TopDockWidgetArea |
            Qt.DockWidgetArea.BottomDockWidgetArea
        )
        
        # Set up features
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        
        # Set up size
        self.resize(800, 600)
        
    def closeEvent(self, event):
        """Handle close event."""
        # Clean up resources
        if hasattr(self, 'web_view'):
            self.web_view.deleteLater()
        elif hasattr(self, 'pdf_view'):
            self.pdf_view.deleteLater()
        super().closeEvent(event)

class MainWindow(QMainWindow):
    """Main application window with multi-pane interface."""
    
    # Define signals
    document_changed = pyqtSignal(int)
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        
        # Flag to track initialization status
        self._initialization_complete = False
        
        self.setWindowTitle("Incrementum - Knowledge Management System")
        
        # Set application icon
        self._set_application_icon()
        
        # Initialize database session
        self.db_session = init_database()
        
        # Initialize settings manager
        self.settings_manager = SettingsManager()
        
        # Initialize models
        self.document_model = DocumentModel(self.db_session)
        self.category_model = CategoryModel(self.db_session)
        
        # Initialize managers
        self.extract_processor = ExtractProcessor(self.db_session)
        self.item_generator = LearningItemGenerator(self.extract_processor)
        self.document_processor = DocumentProcessor(self.db_session)
        self.export_manager = ExportManager(self.db_session)
        self.network_builder = KnowledgeNetworkBuilder(self.db_session)
        self.theme_manager = ThemeManager(self.settings_manager)
        self.queue_manager = FSRSAlgorithm(self.db_session)
        self.rss_manager = RSSFeedManager(self.db_session, self.settings_manager)
        self.tag_manager = TagManager(self.db_session)  
        self.spaced_repetition = self.queue_manager 

        # Set window properties
        self.setMinimumSize(1200, 800)
        
        # Create UI components in proper order
        self._create_actions()
        
        # CRITICAL: Create the menu bar with basic structure first
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)
        
        # Create menu references that will be needed by other methods
        self.file_menu = menu_bar.addMenu("&File")
        self.edit_menu = menu_bar.addMenu("&Edit")
        self.view_menu = menu_bar.addMenu("&View")
        self.learning_menu = menu_bar.addMenu("&Learning")
        self.tools_menu = menu_bar.addMenu("&Tools")
        self.help_menu = menu_bar.addMenu("&Help")
        
        # Now that menus exist, we can create the toolbar
        self._create_tool_bar()
        
        # Create other UI elements
        self._create_status_bar()
        self._create_central_widget()
        self._create_docks()
        
        # Now that view_menu exists, set up dock options
        self._setup_dock_options()
        
        # Populate menus with actions
        self._create_menus()
        
        # Initialize recent files menu - now handled in _create_menus()
        # self.recent_files_menu = QMenu("Recent Files", self)
        # self.file_menu.addMenu(self.recent_files_menu)
        self._update_recent_files_menu()
        
        # Rest of initialization
        self._load_recent_documents()
        self._update_status()
        self._restore_saved_layout()
        self._restore_session()
        self._setup_auto_save()
        self._apply_settings()
        self._check_startup_statistics()
        self._start_rss_updater()
        
        # Initialization is complete
        self._initialization_complete = True
        
        # Add a timer to save session after the window is shown
        QTimer.singleShot(1000, self._check_session_state)
        
        # Connect exit action
        self.action_exit.triggered.connect(self.close)

    def _set_application_icon(self):
        """Set application icon based on platform."""
        import platform
        import os
        from PyQt6.QtGui import QIcon
        from PyQt6.QtCore import QSize
        
        # Base path for icons
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                "assets", "icons")
        
        # Detect platform
        system = platform.system().lower()
        
        if system == "windows":
            # Windows uses .ico files
            icon_file = os.path.join(icon_path, "incrementum.ico")
            if os.path.exists(icon_file):
                app_icon = QIcon(icon_file)
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)  # Set application-wide
        elif system == "darwin":  # macOS
            # macOS can use large PNG icons
            icon_file = os.path.join(icon_path, "incrementum.png") 
            if os.path.exists(icon_file):
                app_icon = QIcon(icon_file)
                self.setWindowIcon(app_icon)
                QApplication.setWindowIcon(app_icon)  # Set application-wide
        else:  # Linux and others
            # Linux typically uses various sized PNGs
            icon = QIcon()
            # Add multiple sizes for proper scaling
            for size in [16, 22, 24, 32, 48, 64, 128, 256]:
                icon_file = os.path.join(icon_path, f"incrementum_{size}.png")
                if os.path.exists(icon_file):
                    icon.addFile(icon_file, QSize(size, size))
            
            # Set the icon if we added any files
            if not icon.isNull():
                self.setWindowIcon(icon)
                # On Linux/X11, also set the application-wide icon
                # This makes the icon appear in task bars, etc.
                QApplication.setWindowIcon(icon)
                
        # Also set application name and organization for proper desktop integration
        QApplication.setApplicationName("Incrementum")
        QApplication.setOrganizationName("Incrementum")
        QApplication.setApplicationDisplayName("Incrementum - Incremental Learning System")
    
    def _check_session_state(self):
        """Debug check of session state after window is shown."""
        logger.info(f"Content tabs widget exists: {hasattr(self, 'content_tabs')}")
        if hasattr(self, 'content_tabs'):
            logger.info(f"Content tabs count: {self.content_tabs.count()}")
            self._save_session()
        else:
            logger.error("Content tabs widget not found during session state check")
    
    def _restore_session(self):
        """Restore the previous session's open tabs and active document."""
        try:
            # Get saved session data from settings
            session_data = self.settings_manager.get_setting("session", "open_tabs", None)
            
            if not session_data:
                # No saved session data
                logger.info("No saved session data found to restore")
                return
            
            # Make sure we have a tab widget
            if not hasattr(self, 'content_tabs') or not self.content_tabs:
                logger.warning("No tab widget found, session not restored")
                return
                
            # Parse the session data
            tabs_data = json.loads(session_data)
            logger.info(f"Attempting to restore session with {len(tabs_data)} tabs")
            
            # Restore tabs
            for tab_data in tabs_data:
                tab_type = tab_data.get("type")
                item_id = tab_data.get("id")
                
                if not tab_type:
                    logger.warning(f"Missing tab type in session data: {tab_data}")
                    continue
                    
                if tab_type == "document":
                    if item_id:
                        logger.info(f"Restoring document tab: {item_id}")
                        self._open_document(item_id)
                    else:
                        logger.warning("Document ID missing in session data")
                elif tab_type == "extract":
                    if item_id:
                        logger.info(f"Restoring extract tab: {item_id}")
                        self._open_extract(item_id)
                    else:
                        logger.warning("Extract ID missing in session data")
                elif tab_type == "learning_item":
                    if item_id:
                        logger.info(f"Restoring learning item tab: {item_id}")
                        self._open_learning_item(item_id)
                    else:
                        logger.warning("Learning item ID missing in session data")
                elif tab_type == "web":
                    # Special handling for web browser tabs
                    url = tab_data.get("url")
                    if url:
                        logger.info(f"Restoring web tab: {url}")
                        web_view = WebBrowserView(self.db_session, self)
                        web_view.load_url(url)
                        self.content_tabs.addTab(web_view, f"Web: {tab_data.get('title', url)}")
                    else:
                        logger.warning("Web URL missing in session data")
                else:
                    logger.warning(f"Unknown tab type in session data: {tab_type}")
            
            # Set active tab
            active_tab = self.settings_manager.get_setting("session", "active_tab", 0)
            if active_tab < self.content_tabs.count():
                self.content_tabs.setCurrentIndex(active_tab)
                logger.info(f"Set active tab to index {active_tab}")
            else:
                logger.warning(f"Active tab index {active_tab} out of range ({self.content_tabs.count()} tabs)")
                
            logger.info(f"Restored session with {len(tabs_data)} tabs")
            
        except Exception as e:
            logger.exception(f"Error restoring session: {e}")
    
    def _save_session(self):
        """Save the current session's open tabs and active document."""
        # Skip if initialization is not complete
        if not hasattr(self, '_initialization_complete') or not self._initialization_complete:
            return
            
        try:
            tabs_data = []
            
            # Save information about each open tab
            if hasattr(self, 'content_tabs') and self.content_tabs:
                logger.info(f"Saving session with {self.content_tabs.count()} tabs")
                
                for i in range(self.content_tabs.count()):
                    tab_widget = self.content_tabs.widget(i)
                    tab_info = {"type": "unknown", "id": None}
                    
                    # Different handling based on tab type
                    if isinstance(tab_widget, DocumentView):
                        tab_info["type"] = "document"
                        tab_info["id"] = tab_widget.document_id
                        logger.info(f"  Saving document tab: {tab_widget.document_id}")
                    elif isinstance(tab_widget, ExtractView):
                        tab_info["type"] = "extract" 
                        tab_info["id"] = tab_widget.extract_id
                        logger.info(f"  Saving extract tab: {tab_widget.extract_id}")
                    elif isinstance(tab_widget, LearningItemEditor):
                        tab_info["type"] = "learning_item"
                        tab_info["id"] = tab_widget.item_id
                        logger.info(f"  Saving learning item tab: {tab_widget.item_id}")
                    elif isinstance(tab_widget, WebBrowserView):
                        tab_info["type"] = "web"
                        tab_info["url"] = tab_widget.current_url
                        tab_info["title"] = self.content_tabs.tabText(i).replace("Web: ", "")
                        logger.info(f"  Saving web tab: {tab_widget.current_url}")
                    else:
                        # Skip unknown tab types
                        logger.info(f"  Skipping unknown tab type: {type(tab_widget).__name__}")
                        continue
                    
                    tabs_data.append(tab_info)
                
                # Save the session data
                self.settings_manager.set_setting("session", "open_tabs", json.dumps(tabs_data))
                
                # Save the active tab index
                self.settings_manager.set_setting("session", "active_tab", self.content_tabs.currentIndex())
                
                # Force save settings to disk immediately
                self.settings_manager.save_settings()
                
                logger.info(f"Saved session with {len(tabs_data)} tabs")
            else:
                logger.warning("No tab widget found, session not saved")
                
        except Exception as e:
            logger.exception(f"Error saving session: {e}")
    
    def closeEvent(self, event):
        """Handle the window close event to save session state."""
        logger.info("Application closing, saving session state...")
        
        try:
            # Stop RSS feed updater
            if hasattr(self, 'rss_manager'):
                try:
                    self.rss_manager.stop_feed_update_timer()
                    logger.info("Stopped RSS feed updater")
                except Exception as e:
                    logger.error(f"Error stopping RSS feed updater: {e}")
            
            # Save the current layout
            layout_data = self.saveState().toBase64().data().decode()
            self.settings_manager.set_setting("ui", "dock_layout", layout_data)
            
            # Save the current session
            self._save_session()
            
            # Save any open document states
            if hasattr(self, 'content_tabs') and self.content_tabs:
                for i in range(self.content_tabs.count()):
                    tab_widget = self.content_tabs.widget(i)
                    
                    # Save document position if it's a document view
                    if isinstance(tab_widget, DocumentView) and hasattr(tab_widget, '_save_position'):
                        tab_widget._save_position()
                    elif isinstance(tab_widget, PDFViewWidget) and hasattr(tab_widget, '_save_position'):
                        tab_widget._save_position()
            
            # Look for any open dock widgets that might be PDFViewWidget
            for dock in self.findChildren(DockablePDFView):
                if hasattr(dock, 'pdf_widget') and hasattr(dock.pdf_widget, '_save_position'):
                    dock.pdf_widget._save_position()
            
            # Force settings to be saved immediately
            self.settings_manager.save_settings()
            
            logger.info("Application state saved")
            
            # Stop any timers
            if hasattr(self, 'auto_save_timer') and self.auto_save_timer.isActive():
                self.auto_save_timer.stop()
                
        except Exception as e:
            logger.exception(f"Error during application shutdown: {e}")
        
        # Accept the event to close the window
        event.accept()
    
    def _restore_saved_layout(self):
        """Restore the saved dock layout if available."""
        # Get saved layout from settings
        layout_data = self.settings_manager.get_setting("ui", "dock_layout", None)
        
        if layout_data:
            try:
                # Restore layout state
                self.restoreState(QByteArray.fromBase64(layout_data.encode()))
                logger.info("Restored saved layout")
            except Exception as e:
                logger.error(f"Failed to restore saved layout: {e}")
                # Fall back to default layout
    
    def _create_actions(self):
        """Create and set up the application actions."""
        # File menu actions
        self.action_import_file = QAction("Import Document...", self)
        self.action_import_file.setShortcut(QKeySequence("Ctrl+O"))
        self.action_import_file.triggered.connect(self._on_import_file)
        
        self.action_import_url = QAction("Import URL...", self)
        self.action_import_url.setShortcut(QKeySequence("Ctrl+U"))
        self.action_import_url.triggered.connect(self._on_import_url)
        
        self.action_import_arxiv = QAction("Import arXiv Paper...", self)
        self.action_import_arxiv.triggered.connect(self._on_import_arxiv)
        
        self.action_import_knowledge = QAction("Import Knowledge...", self)
        self.action_import_knowledge.triggered.connect(self._on_import_knowledge)
        
        self.action_export_knowledge = QAction("Export Knowledge...", self)
        self.action_export_knowledge.triggered.connect(self._on_export_knowledge)
        
        self.action_export_all_data = QAction("Export All Data...", self)
        self.action_export_all_data.triggered.connect(self._on_export_all_data)
        
        # Add the missing save action
        self.action_save = QAction("Save", self)
        self.action_save.setShortcut(QKeySequence("Ctrl+S"))
        self.action_save.setIcon(QIcon.fromTheme("document-save"))
        self.action_save.triggered.connect(self._on_save)
        
        # Add Save As action
        self.action_save_as = QAction("Save As...", self)
        self.action_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.action_save_as.triggered.connect(self._on_save_as)
        
        # Add Export to PDF action
        self.action_export_pdf = QAction("Export as PDF...", self)
        self.action_export_pdf.triggered.connect(self._on_export_pdf)
        
        # Create Recent Files menu
        self.recent_files_menu = QMenu("Recent Files", self)
        self.action_clear_recent = QAction("Clear Recent Files", self)
        self.action_clear_recent.triggered.connect(self._on_clear_recent_files)
        
        self.action_exit = QAction("Exit", self)
        self.action_exit.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_exit.triggered.connect(self.close)
        
        # Edit menu actions
        self.action_new_extract = QAction("New Extract...", self)
        self.action_new_extract.setShortcut(QKeySequence("Ctrl+E"))
        self.action_new_extract.triggered.connect(self._on_new_extract)
        
        self.action_new_learning_item = QAction("New Learning Item...", self)
        self.action_new_learning_item.setShortcut(QKeySequence("Ctrl+L"))
        self.action_new_learning_item.triggered.connect(self._on_new_learning_item)
        
        self.action_manage_tags = QAction("Manage Tags...", self)
        self.action_manage_tags.triggered.connect(self._on_manage_tags)
        
        # View menu actions - panel toggles
        self.action_toggle_category_panel = QAction("Category Panel", self)
        self.action_toggle_category_panel.setCheckable(True)
        self.action_toggle_category_panel.setChecked(True)
        self.action_toggle_category_panel.triggered.connect(self._on_toggle_category_panel)
        
        self.action_toggle_search_panel = QAction("Search Panel", self)
        self.action_toggle_search_panel.setCheckable(True)
        self.action_toggle_search_panel.setChecked(True)
        self.action_toggle_search_panel.triggered.connect(self._on_toggle_search_panel)
        
        self.action_toggle_stats_panel = QAction("Statistics Panel", self)
        self.action_toggle_stats_panel.setCheckable(True)
        self.action_toggle_stats_panel.setChecked(True)
        self.action_toggle_stats_panel.triggered.connect(self._on_toggle_stats_panel)
        
        self.action_toggle_queue_panel = QAction("Reading Queue Panel", self)
        self.action_toggle_queue_panel.setCheckable(True)
        self.action_toggle_queue_panel.setChecked(True)
        self.action_toggle_queue_panel.triggered.connect(self._on_toggle_queue_panel)
        
        # Add Knowledge Tree panel toggle action
        self.action_toggle_knowledge_tree = QAction("Knowledge Tree Panel", self)
        self.action_toggle_knowledge_tree.setCheckable(True)
        self.action_toggle_knowledge_tree.setChecked(True)
        self.action_toggle_knowledge_tree.triggered.connect(self._on_toggle_knowledge_tree)
        
        # Queue and document navigation
        self.action_read_next = QAction("Read Next in Queue", self)
        self.action_read_next.triggered.connect(self._on_read_next)
        
        self.action_prev_document = QAction("Previous Document", self)
        self.action_prev_document.setShortcut(ShortcutManager.PREV_DOCUMENT)
        self.action_prev_document.triggered.connect(self._on_prev_document)
        
        self.action_next_document = QAction("Next Document", self)
        self.action_next_document.setShortcut(ShortcutManager.NEXT_DOCUMENT)
        self.action_next_document.triggered.connect(self._on_read_next)
        
        # Learning menu actions
        self.action_start_review = QAction("Start Review Session", self)
        self.action_start_review.setShortcut(ShortcutManager.START_REVIEW)
        self.action_start_review.triggered.connect(self._on_start_review)
        
        self.action_browse_extracts = QAction("Browse Extracts", self)
        self.action_browse_extracts.triggered.connect(self._on_browse_extracts)
        
        self.action_browse_learning_items = QAction("Browse Learning Items", self)
        self.action_browse_learning_items.triggered.connect(self._on_browse_learning_items)
        
        self.action_generate_items = QAction("Generate Learning Items", self)
        self.action_generate_items.setShortcut(ShortcutManager.GENERATE_ITEMS)
        self.action_generate_items.triggered.connect(self._on_generate_items)
        
        # Tools menu actions
        self.action_search = QAction("Search...", self)
        self.action_search.setShortcut(ShortcutManager.SEARCH)
        self.action_search.triggered.connect(self._on_search)
        
        self.action_view_network = QAction("Knowledge Network", self)
        self.action_view_network.triggered.connect(self._on_view_network)
        
        self.action_backup_restore = QAction("Backup & Restore", self)
        self.action_backup_restore.triggered.connect(self._on_backup_restore)
        
        self.action_settings = QAction("Settings...", self)
        self.action_settings.setShortcut(ShortcutManager.SETTINGS)
        self.action_settings.triggered.connect(self._on_show_settings)
        
        self.action_statistics = QAction("Statistics Dashboard", self)
        self.action_statistics.triggered.connect(self._on_show_statistics)
        
        # Help actions
        self.action_keyboard_shortcuts = QAction("Keyboard Shortcuts", self)
        self.action_keyboard_shortcuts.setShortcut(ShortcutManager.HELP)
        self.action_keyboard_shortcuts.triggered.connect(self._on_show_shortcuts)

        # New actions
        self.action_summarize_document = QAction("Summarize Document...", self)
        self.action_summarize_document.triggered.connect(self._on_summarize_document)
        self.action_summarize_document.setEnabled(False)

        # Tools menu actions
        self.action_view_queue = QAction("Reading Queue", self)
        self.action_view_queue.setShortcut(QKeySequence("Ctrl+Q"))
        self.action_view_queue.triggered.connect(self._on_view_queue)
        
        # Dock management actions
        self.action_tile_docks = QAction("Tile PDF Viewers", self)
        self.action_tile_docks.triggered.connect(self._on_tile_docks)
        
        self.action_cascade_docks = QAction("Cascade PDF Viewers", self)
        self.action_cascade_docks.triggered.connect(self._on_cascade_docks)
        
        self.action_tab_docks = QAction("Tab PDF Viewers", self)
        self.action_tab_docks.triggered.connect(self._on_tab_docks)

        # Add toolbar toggle action
        self.action_toggle_toolbar = QAction("Toolbar", self)
        self.action_toggle_toolbar.setCheckable(True)
        self.action_toggle_toolbar.setChecked(True)
        self.action_toggle_toolbar.triggered.connect(self._on_toggle_toolbar)
        
        # Import actions
        self.action_import_file = QAction("Import File", self)
        self.action_import_file.setStatusTip("Import a document from a file")
        self.action_import_file.triggered.connect(self._on_import_file)
        
        self.action_import_url = QAction("Import URL", self)
        self.action_import_url.setStatusTip("Import a document from a URL")
        self.action_import_url.triggered.connect(self._on_import_url)
        
        self.action_import_knowledge = QAction("Import Knowledge", self)
        self.action_import_knowledge.setStatusTip("Import knowledge from other sources")
        self.action_import_knowledge.triggered.connect(self._on_import_knowledge)
        
        self.action_web_browser = QAction("Web Browser", self)
        self.action_web_browser.setStatusTip("Browse the web and create extracts")
        self.action_web_browser.setShortcut(QKeySequence("Ctrl+B"))
        self.action_web_browser.triggered.connect(self._on_open_web_browser)

        # Tools menu actions
        self.action_tag_manager = QAction("Tag Manager", self)
        self.action_tag_manager.triggered.connect(self._on_manage_tags)
        
        self.action_batch_processor = QAction("Batch Processor", self)
        self.action_batch_processor.triggered.connect(self._on_manage_tags)
        
        self.action_review_manager = QAction("Review Manager", self)
        self.action_review_manager.triggered.connect(self._on_manage_tags)
        
        self.action_backup = QAction("Backup", self)
        self.action_backup.triggered.connect(self._on_backup_restore)
        
        # Add RSS feed manager action
        self.action_rss_feeds = QAction("Manage RSS Feeds", self)
        self.action_rss_feeds.triggered.connect(self._on_manage_rss_feeds)

        # Bookmark action
        self.action_add_bookmark = QAction("Add Bookmark", self)
        self.action_add_bookmark.setShortcut(QKeySequence("Ctrl+B"))
        self.action_add_bookmark.triggered.connect(self._on_add_bookmark)

        # Highlight action
        self.action_highlight = QAction("Highlight Selection", self)
        self.action_highlight.setShortcut(QKeySequence("Ctrl+H"))
        self.action_highlight.triggered.connect(self._on_highlight_selection)
        
        # YouTube Playlists action
        self.action_youtube_playlists = QAction(QIcon.fromTheme("video-display"), "YouTube Playlists", self)
        self.action_youtube_playlists.setStatusTip("Manage YouTube playlists")
        self.action_youtube_playlists.triggered.connect(self.open_youtube_playlists)
        
        # Add Switch action for the toolbar
        self.action_switch = QAction("Switch", self)
        self.action_switch.setStatusTip("Switch between documents")
        
        # Add Sync with Cloud action
        self.action_sync_with_cloud = QAction("Sync with Cloud", self)
        self.action_sync_with_cloud.triggered.connect(self._on_sync_with_cloud)
        
    def _start_rss_updater(self):
        """Start the RSS feed update timer if enabled."""
        try:
            # Check if RSS feeds are enabled
            rss_enabled = self.settings_manager.get_setting("rss", "enabled", True)
            
            if rss_enabled:
                # Start the RSS feed updater
                self.rss_manager.start_feed_update_timer()
                logger.info("Started RSS feed updater")
        except Exception as e:
            logger.error(f"Error starting RSS feed updater: {e}")
    
    @pyqtSlot()
    def _on_manage_rss_feeds(self):
        """Open the RSS feed management dialog."""
        try:
            dialog = RSSFeedDialog(self.db_session, self.rss_manager, self)
            dialog.feedsUpdated.connect(self._on_feeds_updated)
            dialog.exec()
            
        except Exception as e:
            logger.exception(f"Error opening RSS feed manager: {e}")
            QMessageBox.critical(
                self, "Error",
                f"Error opening RSS feed manager: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_feeds_updated(self):
        """Handle updates to RSS feeds."""
        # Refresh any views that might display RSS content
        self._update_queue_widget()
        
        # If queue view is open, refresh it
        if hasattr(self, 'queue_view'):
            self.queue_view._load_queue_data()
    
    def _update_queue_widget(self):
        """Update the queue widget with current data."""
        # This will be called when RSS feeds are updated
        if hasattr(self, 'queue_view'):
            try:
                self.queue_view._load_queue_data()
            except Exception as e:
                logger.error(f"Error updating queue widget after RSS update: {e}")
    
    @pyqtSlot()
    def _on_save(self):
        """Save the current item."""
        current_widget = self.content_tabs.currentWidget()
        
        # Check what type of widget we have and call appropriate save method
        if hasattr(current_widget, 'save_item') and callable(current_widget.save_item):
            current_widget.save_item()
        elif isinstance(current_widget, ExtractView):
            if hasattr(current_widget, '_on_save'):
                current_widget._on_save()
        elif isinstance(current_widget, LearningItemEditor):
            if hasattr(current_widget, '_on_save'):
                current_widget._on_save()
        else:
            self.status_label.setText("Nothing to save in current tab")

    @pyqtSlot()
    def _on_add_bookmark(self):
        """Add a bookmark at the current location."""
        current_widget = self.content_tabs.currentWidget()
        
        # Check if current widget is a PDF viewer
        if isinstance(current_widget, PDFViewWidget):
            if hasattr(current_widget, '_on_add_bookmark'):
                current_widget._on_add_bookmark()
        else:
            self.status_label.setText("Can only add bookmarks in document view")

    @pyqtSlot()
    def _on_highlight_selection(self):
        """Highlight the current selection."""
        current_widget = self.content_tabs.currentWidget()
        
        # Check if current widget is a PDF viewer
        if isinstance(current_widget, PDFViewWidget):
            # If PDF viewer has the pdf_view attribute with add_highlight method
            if hasattr(current_widget, 'pdf_view') and hasattr(current_widget.pdf_view, 'add_highlight'):
                current_widget.pdf_view.add_highlight()
                self.status_label.setText("Selection highlighted")
        else:
            self.status_label.setText("Can only highlight in document view")

    @pyqtSlot()
    def _on_generate_items(self):
        """Generate learning items from the current extract."""
        current_widget = self.content_tabs.currentWidget()
        
        # Check if current widget is an extract view
        if isinstance(current_widget, ExtractView):
            if hasattr(current_widget, '_on_generate_items'):
                current_widget._on_generate_items()
        else:
            self.status_label.setText("Can only generate items from extract view")

    @pyqtSlot()
    def _on_show_shortcuts(self):
        """Show keyboard shortcuts help dialog."""
        shortcuts = ShortcutManager.get_shortcut_descriptions()
        
        # Build HTML content for the dialog
        html_content = "<html><body><h2>Keyboard Shortcuts</h2>"
        
        for category, items in shortcuts.items():
            html_content += f"<h3>{category}</h3>"
            for item in items:
                html_content += f"<p>{item['description']}: {item['shortcut']}</p>"
        
        html_content += "</body></html>"
        
            
   
    def _create_menu_bar(self):
        """Create the application menu bar."""
        # ... existing code ...
        
        # View Menu
        self.view_menu = self.menuBar().addMenu("&View")
        
        # Add theme submenu
        self.theme_menu = self.view_menu.addMenu("Themes")
        self._setup_theme_menu()
        
        # We'll add panels menu later in the complete menu bar setup
        
        # ... rest of existing code ...
    
    def _setup_theme_menu(self):
        """Set up the theme selection menu with all available themes."""
        if not hasattr(self, 'theme_manager'):
            self.theme_manager = ThemeManager(self.settings_manager)
            
        # Clear existing actions
        self.theme_menu.clear()
        
        # Get all available themes
        themes = self.theme_manager.get_available_themes()
        
        # Create a theme action group for radio button behavior
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)
        
        # Add built-in themes first
        self._add_theme_action("Light", "light")
        self._add_theme_action("Dark", "dark")
        self._add_theme_action("System", "system")
        
        # Add separator
        self.theme_menu.addSeparator()
        
        # Add predefined themes
        predefined_themes = [
            ("Incrementum", "incrementum"),  # Our branded theme
            ("Nord", "nord"),
            ("Solarized Light", "solarized_light"),
            ("Solarized Dark", "solarized_dark"),
            ("Dracula", "dracula"),
            ("Cyberpunk", "cyberpunk"),
            ("Material Light", "material_light"),
            ("Material Dark", "material_dark"),
            ("Monokai", "monokai"),
            ("GitHub Light", "github_light"),
            ("GitHub Dark", "github_dark"),
            ("Pastel", "pastel")
        ]
        
        for display_name, theme_name in predefined_themes:
            self._add_theme_action(display_name, theme_name)
        
        # Add separator
        self.theme_menu.addSeparator()
        
        # Add actions for custom themes
        custom_themes = [t for t in themes if t not in ["light", "dark", "system", "nord", 
                                                      "solarized_light", "solarized_dark", 
                                                      "dracula", "cyberpunk", "material_light", 
                                                      "material_dark", "monokai", "github_light", 
                                                      "github_dark", "pastel", "incrementum"]]
        
        if custom_themes:
            for theme_name in custom_themes:
                # Make the display name more readable
                display_name = theme_name.replace('_', ' ').title()
                self._add_theme_action(f"Custom: {display_name}", theme_name)
            
            self.theme_menu.addSeparator()
        
        # Add option to create/import custom themes
        create_theme_action = QAction("Create New Theme...", self)
        create_theme_action.triggered.connect(self._on_create_theme)
        self.theme_menu.addAction(create_theme_action)
        
        import_theme_action = QAction("Import Theme...", self)
        import_theme_action.triggered.connect(self._on_import_theme)
        self.theme_menu.addAction(import_theme_action)
        
        # Update checked state based on current theme
        self._update_theme_menu()
    
    def _add_theme_action(self, display_name, theme_name):
        """Add a theme action to the theme menu.
        
        Args:
            display_name (str): Display name for the action
            theme_name (str): Name of the theme to apply
        """
        action = QAction(display_name, self)
        action.setCheckable(True)
        action.setData(theme_name)
        action.triggered.connect(lambda: self._on_theme_selected(theme_name))
        self.theme_action_group.addAction(action)
        self.theme_menu.addAction(action)
        
    def _update_theme_menu(self):
        """Update the checked state of theme menu actions based on current theme."""
        if not hasattr(self, 'theme_menu'):
            return
            
        current_theme = self.settings_manager.get_setting("ui", "theme", "light")
        
        # Find and check the correct action
        for action in self.theme_action_group.actions():
            theme_name = action.data()
            action.setChecked(theme_name == current_theme)
    
    @pyqtSlot(str)
    def _on_theme_selected(self, theme_name):
        """Handle theme selection from menu.
        
        Args:
            theme_name (str): Name of the selected theme
        """
        # Update settings
        self.settings_manager.set_setting("ui", "theme", theme_name)
        self.settings_manager.set_setting("ui", "custom_theme", False)  # Not using custom path
        
        # Apply the theme
        app = QApplication.instance()
        if app and hasattr(self, 'theme_manager'):
            self.theme_manager.apply_theme(app, theme_name)
            
            # Show a brief notification
            self.statusBar().showMessage(f"Theme changed to {theme_name}", 3000)
    
    @pyqtSlot()
    def _on_create_theme(self):
        """Create a new custom theme."""
        if not hasattr(self, 'theme_manager'):
            self.theme_manager = ThemeManager(self.settings_manager)
            
        # Ask for file name and location
        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setNameFilter("Theme Files (*.json)")
        file_dialog.setDefaultSuffix("json")
        
        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            if file_path:
                # Create the theme template
                success = self.theme_manager.create_theme_template(file_path)
                
                if success:
                    # Ask if the user wants to apply the theme
                    reply = QMessageBox.question(
                        self, "Theme Created", 
                        f"Theme template created at {file_path}. Do you want to apply this theme now?\n\n"
                        "Note: You may want to edit the theme file first to customize colors.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        # Get the theme name from file
                        theme_name = os.path.basename(file_path).split('.')[0]
                        
                        # Update settings
                        self.settings_manager.set_setting("ui", "theme", theme_name)
                        self.settings_manager.set_setting("ui", "custom_theme", True)
                        self.settings_manager.set_setting("ui", "theme_file", file_path)
                        
                        # Apply the theme
                        app = QApplication.instance()
                        if app:
                            self.theme_manager.apply_theme(app)
                    
                    # Update theme menu
                    self._setup_theme_menu()
                else:
                    QMessageBox.warning(
                        self, "Error", 
                        f"Failed to create theme template at {file_path}."
                    )
    
    @pyqtSlot()
    def _on_import_theme(self):
        """Import a custom theme from a file."""
        # Ask for theme file
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter("Theme Files (*.json *.qss)")
        
        if file_dialog.exec():
            file_path = file_dialog.selectedFiles()[0]
            if file_path:
                # Get the theme name from file
                theme_name = os.path.basename(file_path).split('.')[0]
                
                # Copy to theme directory
                if not hasattr(self, 'theme_manager'):
                    self.theme_manager = ThemeManager(self.settings_manager)
                    
                theme_dir = self.theme_manager._get_theme_directory()
                theme_dir.mkdir(parents=True, exist_ok=True)
                
                if file_path.endswith('.json'):
                    dest_path = theme_dir / f"{theme_name}.json"
                else:
                    dest_path = theme_dir / f"{theme_name}.qss"
                
                try:
                    import shutil
                    shutil.copy2(file_path, dest_path)
                    
                    # Ask if the user wants to apply the theme
                    reply = QMessageBox.question(
                        self, "Theme Imported", 
                        f"Theme imported successfully. Do you want to apply this theme now?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        # Update settings
                        self.settings_manager.set_setting("ui", "theme", theme_name)
                        self.settings_manager.set_setting("ui", "custom_theme", False)
                        
                        # Apply the theme
                        app = QApplication.instance()
                        if app:
                            self.theme_manager.apply_theme(app, theme_name)
                    
                    # Update theme menu
                    self._setup_theme_menu()
                    
                except Exception as e:
                    QMessageBox.warning(
                        self, "Import Error", 
                        f"Failed to import theme: {str(e)}"
                    )

    def _create_tool_bar(self):
        """Create and setup the toolbar."""
        self.tool_bar = QToolBar("Main Toolbar", self)
        self.tool_bar.setObjectName("MainToolBar")
        self.tool_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.tool_bar.setIconSize(QSize(32, 32))
        self.addToolBar(self.tool_bar)
        
        # Set visibility based on settings
        toolbar_visible = self.settings_manager.get_setting("ui", "toolbar_visible", True)
        self.tool_bar.setVisible(toolbar_visible)
        
        # Add actions to toolbar with icons
        
        # File actions
        file_section = QToolButton()
        file_section.setText("File")
        file_section.setIcon(QIcon.fromTheme("document-open", 
                                       self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogStart)))
        file_section.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        file_section.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        
        file_menu = QMenu(file_section)
        file_menu.addAction(self.action_import_file)
        file_menu.addAction(self.action_import_url)
        file_menu.addAction(self.action_import_arxiv)
        file_menu.addAction(self.action_web_browser)
        
        file_section.setMenu(file_menu)
        self.tool_bar.addWidget(file_section)
        
        # Import document action
        self.action_import_file.setIcon(QIcon.fromTheme("document-open", 
                                       self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogStart)))
        self.tool_bar.addAction(self.action_import_file)
        
        # Import URL action
        self.action_import_url.setIcon(QIcon.fromTheme("web-browser", 
                                      self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)))
        self.tool_bar.addAction(self.action_import_url)
        
        # Add separator
        self.tool_bar.addSeparator()
        
        # Read Next action
        self.action_read_next.setIcon(QIcon.fromTheme("go-next", 
                                     self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight)))
        self.tool_bar.addAction(self.action_read_next)
        
        # Start Review action
        self.action_start_review.setIcon(QIcon.fromTheme("view-refresh", 
                                        self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)))
        self.tool_bar.addAction(self.action_start_review)
        
        # Add separator
        self.tool_bar.addSeparator()
        
        # Add web browser action if enabled
        if self.settings_manager.get_setting("ui", "web_browser_enabled", True):
            self.action_web_browser.setIcon(QIcon.fromTheme("applications-internet", 
                                          self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)))
            self.tool_bar.addAction(self.action_web_browser)
            self.tool_bar.addSeparator()
        
        # Add Reading Queue button with custom appearance
        self.reading_queue_btn = QToolButton()
        self.reading_queue_btn.setText("Reading Queue")
        self.reading_queue_btn.setToolTip("Show detailed reading queue")
        self.reading_queue_btn.setIcon(QIcon.fromTheme("view-grid", 
             self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)))
        self.reading_queue_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.reading_queue_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.reading_queue_btn.clicked.connect(self._on_show_detailed_queue)
        self.tool_bar.addWidget(self.reading_queue_btn)
        
        # Add separator
        self.tool_bar.addSeparator()
        
        # Save action
        self.action_save.setIcon(QIcon.fromTheme("document-save", 
                                self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)))
        self.tool_bar.addAction(self.action_save)
        
        # Save As action
        self.action_save_as.setIcon(QIcon.fromTheme("document-save-as", 
                                   self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)))
        self.tool_bar.addAction(self.action_save_as)
        
        self.tool_bar.addSeparator()
        
        # Bookmark action
        self.action_add_bookmark.setIcon(QIcon.fromTheme("bookmark-new", 
                                        self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarNormalButton)))
        self.tool_bar.addAction(self.action_add_bookmark)
        
        # Highlight action
        self.action_highlight.setIcon(QIcon.fromTheme("format-text-color", 
                                     self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)))
        self.tool_bar.addAction(self.action_highlight)
        self.tool_bar.addSeparator()
        
        # Generate items action
        self.action_generate_items.setIcon(QIcon.fromTheme("document-new", 
                                         self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)))
        self.tool_bar.addAction(self.action_generate_items)
        self.tool_bar.addSeparator()
        
        # Previous document action
        self.action_prev_document.setIcon(QIcon.fromTheme("go-previous", 
                                        self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft)))
        self.tool_bar.addAction(self.action_prev_document)
        
        # Add YouTube playlists action
        self.action_youtube_playlists.setIcon(QIcon.fromTheme("video-display",
                                             self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)))
        self.tool_bar.addAction(self.action_youtube_playlists)
        
        # Add RSS feeds action
        self.action_rss_feeds.setIcon(QIcon.fromTheme("application-rss+xml",
                                     self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)))
        self.tool_bar.addAction(self.action_rss_feeds)
        
        self.tool_bar.addSeparator()
        
        # Add Sync with Cloud action
        self.action_sync_with_cloud.setIcon(QIcon.fromTheme("emblem-synchronizing",
                                           self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)))
        self.tool_bar.addAction(self.action_sync_with_cloud)
        
        self.tool_bar.addSeparator()
        
        # Search action
        self.action_search.setIcon(QIcon.fromTheme("edit-find", 
                                 self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView)))
        self.tool_bar.addAction(self.action_search)
        
        # Settings action
        self.action_settings.setIcon(QIcon.fromTheme("preferences-system",
                                   self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)))
        self.tool_bar.addAction(self.action_settings)
   
    def _on_show_detailed_queue(self):
        """Display a dialog with a detailed view of the reading queue."""
        from ui.detailed_queue_view import DetailedQueueView
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Detailed Reading Queue")
        dialog.setWindowIcon(QIcon.fromTheme("view-grid", 
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)))
        dialog.resize(900, 600)
        
        # Create layout
        layout = QVBoxLayout(dialog)
        
        # Create queue view
        queue_view = DetailedQueueView(self.db_session, self.settings_manager)
        
        # Connect document selection signal to handler
        queue_view.documentSelected.connect(lambda doc_id: self._on_queue_document_selected(doc_id, dialog))
        
        # Add to layout
        layout.addWidget(queue_view)
        
        # Add button row
        button_layout = QHBoxLayout()
        
        # Read next button
        read_next_btn = QPushButton("Read Next Document")
        read_next_btn.setIcon(QIcon.fromTheme("go-next", 
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight)))
        read_next_btn.clicked.connect(lambda: self.action_read_next.trigger())
        button_layout.addWidget(read_next_btn)
        
        # Add stretch to push buttons to right
        button_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        # Show dialog
        dialog.exec()
    
    def _on_queue_document_selected(self, document_id, dialog=None):
        """Handle document selection from detailed queue view."""
        try:
            # Load the document
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document with ID {document_id} not found")
                return
                
            # Close the dialog if provided
            if dialog and not dialog.isHidden():
                dialog.accept()
                
            # Open the document
            self._open_document(document.id)
            
        except Exception as e:
            logger.exception(f"Error opening document from queue: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open document: {str(e)}")
    
    def _create_status_bar(self):
        """Create the status bar."""
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        
        self.review_status = QLabel("Due: 0")
        self.status_bar.addPermanentWidget(self.review_status)
    
    def _create_central_widget(self):
        """Create the central widget with tab view."""
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create tab widget for document display
        self.content_tabs = QTabWidget()
        self.content_tabs.setTabsClosable(True)
        self.content_tabs.setMovable(True)
        self.content_tabs.setDocumentMode(True)
        self.content_tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.content_tabs.currentChanged.connect(self._on_tab_changed)
        
        # Enable tracking mouse for middle-click detection
        self.content_tabs.setMouseTracking(True)
        # Install event filter for custom mouse handling
        self.content_tabs.installEventFilter(self)
        
        main_layout.addWidget(self.content_tabs)
        
        self.setCentralWidget(central_widget)
    
    def _create_docks(self):
        """Create dock widgets for various components."""
        # Create category panel
        self.category_dock = QDockWidget("Libraries & Categories", self)
        self.category_dock.setObjectName("CategoryDock")
        self.category_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        
        category_widget = QWidget()
        category_layout = QVBoxLayout(category_widget)
        
        # Create category tree view
        self.category_tree = QTreeView()
        self.category_tree.setModel(self.category_model)
        self.category_tree.setHeaderHidden(True)
        self.category_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.category_tree.customContextMenuRequested.connect(self._on_category_context_menu)
        self.category_tree.clicked.connect(self._on_category_selected)
        category_layout.addWidget(self.category_tree)
        
        # Create document list view below categories
        document_group = QGroupBox("Documents")
        document_layout = QVBoxLayout(document_group)
        
        self.document_list = QListView()
        self.document_list.setModel(self.document_model)
        self.document_list.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.document_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.document_list.customContextMenuRequested.connect(self._on_document_context_menu)
        self.document_list.doubleClicked.connect(self._on_document_activated)
        document_layout.addWidget(self.document_list)
        
        # Add document list to main category layout
        category_layout.addWidget(document_group)
        
        # Set the widget for the dock
        self.category_dock.setWidget(category_widget)
        
        # Add to main window
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.category_dock)
        
        # Create search dock widget
        self.search_dock = QDockWidget("Search", self)
        self.search_dock.setObjectName("SearchDock")
        self.search_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        
        self.search_view = SearchView(self.db_session)
        self.search_view.itemSelected.connect(self._on_search_item_selected)
        self.search_dock.setWidget(self.search_view)
        
        # Add to main window
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.search_dock)
        
        # Create queue dock widget
        self.queue_dock = QDockWidget("Reading Queue", self)
        self.queue_dock.setObjectName("QueueDock")
        self.queue_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        
        self.queue_view = QueueView(self.db_session, self.settings_manager)
        self.queue_view.documentSelected.connect(self._open_document)
        self.queue_dock.setWidget(self.queue_view)
        
        # Add to main window
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.queue_dock)
        
        # Create statistics dock widget
        self.stats_dock = QDockWidget("Statistics Overview", self)
        self.stats_dock.setObjectName("StatsDock")
        self.stats_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        
        self.stats_widget = StatisticsWidget(self.db_session, compact=True)
        self.stats_dock.setWidget(self.stats_widget)
        
        # Add to main window
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.stats_dock)
        
        # Tabify the search and queue docks with the category dock
        self.tabifyDockWidget(self.category_dock, self.search_dock)
        self.tabifyDockWidget(self.category_dock, self.queue_dock)
        
        # Make category dock active by default
        self.category_dock.raise_()
        
        # Removed auto-loading of PDF documents at startup
        # PDF documents will only be opened when explicitly requested by the user
    
    def _setup_dock_options(self):
        """Set up dock widget options and behavior."""
        # Allow dock widgets to be nested and tabbed
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks |
            QMainWindow.DockOption.AllowTabbedDocks |
            QMainWindow.DockOption.AnimatedDocks |
            QMainWindow.DockOption.GroupedDragging
        )

        # Add a menu for layout management
        layout_menu = self.view_menu.addMenu("Layout Management")

        # Add action to reset dock layout
        self.action_reset_layout = QAction("Reset to Default Layout", self)
        self.action_reset_layout.triggered.connect(self._on_reset_layout)
        layout_menu.addAction(self.action_reset_layout)

        # Add action to save current layout
        self.action_save_layout = QAction("Save Current Layout", self)
        self.action_save_layout.triggered.connect(self._on_save_layout)
        layout_menu.addAction(self.action_save_layout)

        # Add action to load saved layout
        self.action_load_layout = QAction("Load Saved Layout", self)
        self.action_load_layout.triggered.connect(self._on_load_layout)
        layout_menu.addAction(self.action_load_layout)

        # Add separator
        self.view_menu.addSeparator()

        # Add action to tile dock widgets
        self.action_tile_docks = QAction("Tile PDF Viewers", self)
        self.action_tile_docks.triggered.connect(self._on_tile_docks)
        self.view_menu.addAction(self.action_tile_docks)

        # Add action to cascade dock widgets
        self.action_cascade_docks = QAction("Cascade PDF Viewers", self)
        self.action_cascade_docks.triggered.connect(self._on_cascade_docks)
        self.view_menu.addAction(self.action_cascade_docks)

        # Add action to tab dock widgets
        self.action_tab_docks = QAction("Tab PDF Viewers", self)
        self.action_tab_docks.triggered.connect(self._on_tab_docks)
        self.view_menu.addAction(self.action_tab_docks)
    
    @pyqtSlot()
    def _on_reset_layout(self):
        """Reset dock widgets to default layout."""
        # Close all docks first
        for dock in self.findChildren(QDockWidget):
            dock.close()
        
        # Re-add docks to their default positions
        if hasattr(self, 'category_dock'):
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.category_dock)
            self.category_dock.setVisible(True)
        
        if hasattr(self, 'search_dock'):
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.search_dock)
            self.search_dock.setVisible(False)
        
        if hasattr(self, 'stats_dock'):
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.stats_dock)
            self.stats_dock.setVisible(False)
        
        if hasattr(self, 'queue_dock'):
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.queue_dock)
            self.queue_dock.setVisible(False)
        
        # Show confirmation
        QMessageBox.information(
            self, "Layout Reset", 
            "The layout has been reset to default positions."
        )
    
    @pyqtSlot()
    def _on_save_layout(self):
        """Save the current dock layout."""
        # Create layout state
        state = self.saveState()
        
        # Save in settings
        self.settings_manager.set_setting("ui", "dock_layout", state.toBase64().data().decode())
        self.settings_manager.save_settings()
        
        # Show confirmation
        QMessageBox.information(
            self, "Layout Saved", 
            "The current layout has been saved and will be restored on next launch."
        )
    
    @pyqtSlot()
    def _on_load_layout(self):
        """Load the saved dock layout."""
        # Get saved layout from settings
        layout_data = self.settings_manager.get_setting("ui", "dock_layout", None)
        
        if not layout_data:
            QMessageBox.information(
                self, "No Saved Layout", 
                "No saved layout found. Save a layout first."
            )
            return
        
        # Restore layout state
        success = self.restoreState(QByteArray.fromBase64(layout_data.encode()))
        
        if success:
            QMessageBox.information(
                self, "Layout Restored", 
                "The saved layout has been restored."
            )
        else:
            QMessageBox.warning(
                self, "Layout Restore Failed", 
                "Failed to restore the saved layout."
            )

    def _load_recent_documents(self):
        """Load and populate recent documents menu."""
        # This is a simplified version - in a real app, we'd load from settings
        self.recent_files_menu.clear()  # Changed from self.recent_menu

        # Get max recent documents from settings
        max_recent = self.settings_manager.get_setting("general", "max_recent_documents", 10)

        # Get recent documents from database
        recent_docs = self.db_session.query(Document).order_by(
            Document.last_accessed.desc()
        ).limit(max_recent).all()

        for doc in recent_docs:
            action = self.recent_files_menu.addAction(doc.title)  # Changed from self.recent_menu
            action.setData(doc.id)
            action.triggered.connect(self._on_recent_document_selected)

   
    def _update_status(self):
        """Update status bar information."""
        # Count due items
        due_count = self.db_session.query(LearningItem).filter(
            (LearningItem.next_review <= datetime.utcnow()) | 
            (LearningItem.next_review == None)
        ).count()
        
        self.review_status.setText(f"Due: {due_count}")
    
    def _setup_auto_save(self):
        """Set up auto-save timer for documents."""
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self._auto_save)
        
        # Get auto-save interval from settings (default to 2 minutes)
        interval = self.settings_manager.get_setting("general", "auto_save_interval", 120000)
        
        # If the interval is in minutes, convert to milliseconds
        if interval < 1000:  # Probably in minutes
            interval = interval * 60 * 1000
        
        logger.info(f"Setting up auto-save with interval: {interval}ms")
        
        # Start the timer if auto-save is enabled
        auto_save_enabled = self.settings_manager.get_setting("general", "auto_save_enabled", True)
        if auto_save_enabled:
            # Use a longer interval to reduce unnecessary saves
            self.auto_save_timer.start(interval)
        
    def _auto_save(self):
        """Automatically save all open documents."""
        # Skip if initialization is not complete
        if not hasattr(self, '_initialization_complete') or not self._initialization_complete:
            logger.debug("Skipping auto-save, initialization not complete")
            return
            
        # Skip if no tabs are open
        if not hasattr(self, 'content_tabs') or not self.content_tabs or self.content_tabs.count() == 0:
            logger.debug("Skipping auto-save, no tabs open")
            return
            
        try:
            logger.debug("Running auto-save...")
            
            # Save the session state (only once every few auto-saves to reduce overhead)
            if hasattr(self, '_auto_save_counter'):
                self._auto_save_counter += 1
                if self._auto_save_counter >= 5:  # Save session every 5th auto-save
                    self._save_session()
                    self._auto_save_counter = 0
            else:
                self._auto_save_counter = 0
                self._save_session()
            
            # Save each open document
            if hasattr(self, 'content_tabs') and self.content_tabs:
                for i in range(self.content_tabs.count()):
                    tab_widget = self.content_tabs.widget(i)
                    
                    # Only save DocumentView and LearningItemEditor widgets
                    if hasattr(tab_widget, 'document') and hasattr(tab_widget, 'document_id'):
                        # Skip YouTube and other web content that doesn't need saving
                        if hasattr(tab_widget, 'document') and tab_widget.document:
                            if hasattr(tab_widget.document, 'content_type') and tab_widget.document.content_type not in ['youtube', 'web']:
                                # Check if the widget has a save_document method
                                if hasattr(tab_widget, 'save_document') and callable(tab_widget.save_document):
                                    try:
                                        tab_widget.save_document()
                                        logger.debug(f"Auto-saved document: {tab_widget.document_id}")
                                    except Exception as e:
                                        logger.error(f"Error saving document {tab_widget.document_id}: {e}")
                                else:
                                    logger.warning(f"Tab widget has no save_document method: {type(tab_widget).__name__}")
                    elif hasattr(tab_widget, 'item_id') and hasattr(tab_widget, 'save_item'):
                        # Learning item editor
                        try:
                            tab_widget.save_item()
                            logger.debug(f"Auto-saved learning item: {tab_widget.item_id}")
                        except Exception as e:
                            logger.error(f"Error saving learning item {tab_widget.item_id}: {e}")
                    
            logger.debug("Auto-save complete")
            
            # Update status
            if hasattr(self, 'status_label'):
                self.status_label.setText(f"Auto-saved at {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            logger.exception(f"Error during auto-save: {e}")
    
    @pyqtSlot(int)
    def _on_arxiv_paper_imported(self, document_id):
        """Handle imported paper from ArXiv."""
        # Open the document
        self._open_document(document_id)
        self._load_recent_documents()
        self._update_status()
        
        # Ask user if they want to summarize the paper
        response = QMessageBox.question(
            self, 
            "Summarize Paper",
            "Would you like to automatically generate a summary of this paper?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if response == QMessageBox.StandardButton.Yes:
            self._show_document_summary(document_id)
    
    def _show_document_summary(self, document_id):
        """Show document summary dialog."""
        try:
            summarize_dialog = SummarizeDialog(self.db_session, document_id, self)
            summarize_dialog.extractCreated.connect(self._on_summary_extract_created)
            summarize_dialog.exec()
        except Exception as e:
            logger.exception(f"Error showing summary dialog: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error generating summary: {str(e)}"
            )
    
    @pyqtSlot(int)
    def _on_summary_extract_created(self, extract_id):
        """Handle extract creation from summary dialog."""
        # Just pass on the extract ID to the existing handler
        # Don't load the Extract object and pass that
        self._on_extract_created(extract_id)
    
    @pyqtSlot()
    def _on_summarize_document(self):
        """Handler for summarizing the current document."""
        # Check if we have an active document tab
        current_tab_idx = self.content_tabs.currentIndex()
        if current_tab_idx < 0:
            QMessageBox.information(
                self, "No Document", 
                "Please open a document first."
            )
            return
            
        # Get the widget and check if it's a document view
        widget = self.content_tabs.widget(current_tab_idx)
        
        # First try to use the document_view's summarize method if available
        # This is especially useful for web content that needs to extract text from the webview
        if hasattr(widget, 'summarize_current_content'):
            widget.summarize_current_content()
            return
            
        # Fallback to the traditional method for regular documents
        if hasattr(widget, 'document') and widget.document:
            self._show_document_summary(widget.document.id)
        else:
            QMessageBox.information(
                self, "Not a Document", 
                "Please select a document tab."
            )
    
    @pyqtSlot(int)
    def _on_tab_changed(self, index):
        """Handler for tab change."""
        if index == -1:
            return  # No tabs
        
        # Get the widget at the current tab
        widget = self.content_tabs.widget(index)
        
        # Update UI based on current tab
        if hasattr(widget, 'document') and hasattr(widget, 'document_id'):
            # It's a document view - enable document actions
            self.action_new_extract.setEnabled(True)
            self.action_add_bookmark.setEnabled(True)
            self.action_highlight.setEnabled(True)
            self.action_summarize_document.setEnabled(True)
            
            # Update the queue view with the current document
            if hasattr(self, 'queue_view'):
                self.queue_view.set_current_document(widget.document_id)
                
            # Emit signal indicating document changed
            self.document_changed.emit(widget.document_id)
            
        elif hasattr(widget, 'extract') and hasattr(widget, 'extract_id'):
            # It's an extract view - enable specific actions
            self.action_new_extract.setEnabled(False)
            self.action_add_bookmark.setEnabled(False)
            self.action_highlight.setEnabled(False)
            self.action_summarize_document.setEnabled(False)
        else:
            # Other kind of tab
            self.action_new_extract.setEnabled(False)
            self.action_add_bookmark.setEnabled(False)
            self.action_highlight.setEnabled(False)
            self.action_summarize_document.setEnabled(False)
    
    def _apply_settings(self):
        """Apply settings to UI."""
        # Category panel visibility
        show_category_panel = self.settings_manager.get_setting("ui", "show_category_panel", True)
        if hasattr(self, 'category_dock') and self.category_dock:
            self.category_dock.setVisible(show_category_panel)
        self.action_toggle_category_panel.setChecked(show_category_panel)
        
        # Apply theme settings
        if not hasattr(self, 'theme_manager'):
            self.theme_manager = ThemeManager(self.settings_manager)
        
        # Apply the theme
        app = QApplication.instance()
        if app:
            # Apply theme and update UI
            current_theme = self.settings_manager.get_setting("ui", "theme", "light")
            self.theme_manager.apply_theme(app, current_theme)
            
            # Update theme menu actions if they exist
            if hasattr(self, 'theme_menu'):
                self._update_theme_menu()
                
            logging.getLogger(__name__).info(f"Applied theme settings, current theme: {self.theme_manager.current_theme}")
    
    def _check_startup_statistics(self):
        """Check if statistics should be shown on startup."""
        show_stats = self.settings_manager.get_setting("general", "startup_show_statistics", False)
        if show_stats:
            self._on_show_statistics()
        
    @pyqtSlot()
    def _on_import_file(self):
        """Handler for importing a file."""
        # Get default directory from settings
        default_dir = self.settings_manager.get_setting("document", "default_document_directory", "")
        
        file_dialog = QFileDialog(self)
        if default_dir:
            file_dialog.setDirectory(default_dir)
        
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter(
            "Documents (*.pdf *.html *.htm *.txt *.epub *.docx);;All Files (*.*)"
        )
        
        if file_dialog.exec():
            file_paths = file_dialog.selectedFiles()
            if file_paths:
                self._import_document(file_paths[0])
    
    @pyqtSlot()
    def _on_import_url(self):
        """Import a document from a URL."""
        dialog = URLImportDialog(parent=self)
        
        if dialog.exec():
            url = dialog.url_line.text().strip()
            if not url:
                return
            
            # Check if this is a YouTube URL - don't use Jina for YouTube
            is_youtube = 'youtube.com' in url or 'youtu.be' in url
                
            # Check if we should use Jina.ai (but not for YouTube)
            use_jina = dialog.use_jina_checkbox.isChecked() and not is_youtube
            
            # Check if we should process with LLM
            process_with_llm = dialog.process_with_llm_checkbox.isChecked() and not is_youtube
            
            # Set up progress bar
            self.statusBar().showMessage(f"Downloading document from {url}...")
            
            # Create a background thread for downloading
            class DownloadThread(QThread):
                downloadFinished = pyqtSignal(int)  # document_id
                downloadFailed = pyqtSignal(str)    # error message
                contentReady = pyqtSignal(str, dict)  # content, metadata
                
                def __init__(self, url, use_jina, process_with_llm, session, settings_manager):
                    super().__init__()
                    self.url = url
                    self.use_jina = use_jina
                    self.process_with_llm = process_with_llm
                    self.session = session
                    self.settings_manager = settings_manager
                
                def run(self):
                    from core.document_processor.document_importer import DocumentImporter
                    importer = DocumentImporter(self.session)
                    
                    try:
                        # Check if this is a YouTube URL - always use YouTube handler
                        if 'youtube.com' in self.url or 'youtu.be' in self.url:
                            from core.document_processor.handlers.youtube_handler import YouTubeHandler
                            youtube_handler = YouTubeHandler()
                            document_id = importer.import_from_url(self.url, handler=youtube_handler)
                            if document_id:
                                self.downloadFinished.emit(document_id)
                            else:
                                self.downloadFailed.emit("Failed to import YouTube video.")
                            return
                                    
                        # If using Jina.ai, import through JinaWebHandler
                        if self.use_jina:
                            from core.document_processor.handlers.jina_web_handler import JinaWebHandler
                            handler = JinaWebHandler(self.settings_manager)
                            
                            # Check if we should process with LLM
                            if self.process_with_llm:
                                # First download the content
                                temp_file, metadata = handler.download_from_url(self.url)
                                
                                if not temp_file:
                                    self.downloadFailed.emit("Failed to download content.")
                                    return
                                
                                # Extract the content
                                content_data = handler.extract_content(temp_file)
                                
                                # Get the text content
                                content = content_data.get('text', '')
                                
                                # Send the content to the main thread for processing with LLM
                                self.contentReady.emit(content, metadata)
                                return
                            else:
                                # Regular Jina import
                                document_id = importer.import_from_url(self.url, handler=handler)
                                if document_id:
                                    self.downloadFinished.emit(document_id)
                                else:
                                    self.downloadFailed.emit("Failed to import document.")
                        else:
                            # Use regular URL import
                            document_id = importer.import_from_url(self.url)
                            if document_id:
                                self.downloadFinished.emit(document_id)
                            else:
                                self.downloadFailed.emit("Failed to import document.")
                    except Exception as e:
                        self.downloadFailed.emit(str(e))
            
            # Create and start the thread
            self.download_thread = DownloadThread(
                url, 
                use_jina, 
                process_with_llm,
                self.db_session, 
                self.settings_manager
            )
            self.download_thread.downloadFinished.connect(self._on_url_download_finished)
            self.download_thread.downloadFailed.connect(self._on_url_download_failed)
            self.download_thread.contentReady.connect(self._on_content_ready)
            self.download_thread.start()
    
    @pyqtSlot(int)
    def _on_url_download_finished(self, document_id):
        """Handle successful URL download."""
        self.statusBar().showMessage("Document imported successfully.")
        
        # Open the document
        self._open_document(document_id)
        
        # Suggest tags if enabled
        if self.settings_manager.get_setting("document", "auto_suggest_tags", True):
            self._auto_suggest_document_tags(document_id)
    
    @pyqtSlot(str)
    def _on_url_download_failed(self, error_message):
        """Handle failed URL download."""
        self.statusBar().showMessage("Import failed.")
        
        QMessageBox.warning(
            self, "Import Error", 
            f"Failed to import document from URL: {error_message}"
        )
    
    @pyqtSlot(str, dict)
    def _on_content_ready(self, content, metadata):
        """Handle content ready from background thread."""
        self.statusBar().showMessage("Content downloaded, processing with LLM...")
        
        # Show the content processor dialog in the main thread
        dialog = ContentProcessorDialog(content, self.settings_manager, self)
        
        # Show the dialog and get result
        if dialog.exec():
            processed_content = dialog.get_processed_content()
            
            if processed_content:
                # Save the processed content to a new file
                import tempfile
                import os
                
                fd, processed_file = tempfile.mkstemp(suffix='.txt')
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(processed_content)
                
                # Create a new document with the processed content
                document = Document(
                    title=metadata.get('title', 'Untitled') + " (Processed)",
                    author=metadata.get('author', ''),
                    file_path=processed_file,
                    content_type="processed_text",
                    source_url=metadata.get('source_url', '')
                )
                
                # Add to session
                self.db_session.add(document)
                self.db_session.commit()
                
                # Open the document
                self._open_document(document.id)
                
                # Auto suggest tags if enabled
                auto_suggest = self.settings_manager.get_setting("document", "auto_suggest_tags", True)
                if auto_suggest:
                    self._auto_suggest_document_tags(document.id)
            else:
                # User canceled or error occurred, try regular import
                self.statusBar().showMessage("LLM processing canceled, falling back to regular import...")
                
                # Import the document normally
                from core.document_processor.document_importer import DocumentImporter
                importer = DocumentImporter(self.db_session)
                
                try:
                    # Create a JinaWebHandler and import
                    from core.document_processor.handlers.jina_web_handler import JinaWebHandler
                    handler = JinaWebHandler(self.settings_manager)
                    
                    document_id = importer.import_from_url(metadata.get('source_url', ''), handler=handler)
                    if document_id:
                        self._on_url_download_finished(document_id)
                    else:
                        self._on_url_download_failed("Failed to import document.")
                except Exception as e:
                    self._on_url_download_failed(str(e))
        else:
            # User canceled dialog, fall back to regular import
            self.statusBar().showMessage("LLM processing canceled, falling back to regular import...")
            
            # Import the document normally
            from core.document_processor.document_importer import DocumentImporter
            importer = DocumentImporter(self.db_session)
            
            try:
                # Create a JinaWebHandler and import
                from core.document_processor.handlers.jina_web_handler import JinaWebHandler
                handler = JinaWebHandler(self.settings_manager)
                
                document_id = importer.import_from_url(metadata.get('source_url', ''), handler=handler)
                if document_id:
                    self._on_url_download_finished(document_id)
                else:
                    self._on_url_download_failed("Failed to import document.")
            except Exception as e:
                self._on_url_download_failed(str(e))
    
    @pyqtSlot()
    def _on_import_knowledge(self):
        """Handler for importing knowledge items."""
        dialog = ImportDialog(self.db_session, self)
        dialog.importCompleted.connect(self._on_import_completed)
        dialog.exec()
    
    @pyqtSlot(int, int, int)
    def _on_import_completed(self, extracts_count, items_count, tags_count):
        """Handler for import completion."""
        self._update_status()
        self.status_label.setText(f"Import completed: {extracts_count} extracts, {items_count} items, {tags_count} tags")
    
    @pyqtSlot()
    def _on_export_knowledge(self):
        """Handler for exporting knowledge items."""
        # Check if we have a current extract or learning item open
        current_extract_id = None
        current_item_id = None
        
        current_widget = self.content_tabs.currentWidget()
        if isinstance(current_widget, ExtractView):
            current_extract_id = current_widget.extract.id if hasattr(current_widget, 'extract') else None
        elif hasattr(current_widget, 'learning_item') and current_widget.learning_item:
            current_item_id = current_widget.learning_item.id
        
        dialog = ExportDialog(self.db_session, [current_extract_id] if current_extract_id else None, 
                             [current_item_id] if current_item_id else None, self)
        dialog.exec()
    
    def _import_document(self, file_path):
        """Import a document file."""
        self.status_label.setText(f"Importing: {os.path.basename(file_path)}...")
        
        # Get selected category (if any)
        category_id = None
        indexes = self.category_tree.selectedIndexes()
        if indexes:
            category_id = self.category_model.get_category_id(indexes[0])
        
        # Get default category from settings if none selected
        if category_id is None:
            category_id = self.settings_manager.get_setting("general", "default_category_id", None)
        
        # This would be done in a background thread in a real app
        document = self.document_processor.import_document(file_path, category_id)
        
        if document:
            self.status_label.setText(f"Imported: {document.title}")
            self._load_recent_documents()
            self._update_status()
            
            # Open the document
            self._open_document(document.id)
            
            # Auto suggest tags if enabled
            auto_suggest = self.settings_manager.get_setting("document", "auto_suggest_tags", True)
            if auto_suggest:
                self._auto_suggest_document_tags(document.id)
        else:
            QMessageBox.warning(
                self, "Import Failed", 
                f"Failed to import: {file_path}"
            )
            self.status_label.setText("Import failed")
    
    def _auto_suggest_document_tags(self, document_id):
        """Auto-suggest tags for a document."""
        suggested_tags = self.tag_manager.suggest_tags_for_document(document_id)
        
        if suggested_tags:
            # Ask user if they want to add these tags
            msg = "Would you like to add the following suggested tags?\n\n"
            msg += ", ".join(suggested_tags)
            
            reply = QMessageBox.question(
                self, "Suggested Tags", 
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Add tags
                for tag in suggested_tags:
                    self.tag_manager.add_document_tag(document_id, tag)
    
    @pyqtSlot()
    def _on_tile_docks(self):
        """Tile all floating dock widgets."""
        # Get all floating PDF dock widgets
        floating_docks = [dock for dock in self.findChildren(DockablePDFView)
                        if dock.isFloating()]

        if not floating_docks:
            return

        # Calculate the desktop area
        desktop = QApplication.desktop()
        available_rect = desktop.availableGeometry(self)

        # Calculate the size for each floating dock
        num_docks = len(floating_docks)
        rows = int(num_docks ** 0.5)
        cols = (num_docks + rows - 1) // rows  # Ceiling division

        width = available_rect.width() // cols
        height = available_rect.height() // rows

        # Position the docks in a grid
        for i, dock in enumerate(floating_docks):
            row = i // cols
            col = i % cols

            x = available_rect.x() + col * width
            y = available_rect.y() + row * height

            dock.setGeometry(x, y, width, height)

    @pyqtSlot()
    def _on_cascade_docks(self):
        """Cascade all floating dock widgets."""
        # Get all floating PDF dock widgets
        floating_docks = [dock for dock in self.findChildren(DockablePDFView)
                        if dock.isFloating()]

        if not floating_docks:
            return

        # Calculate the desktop area
        desktop = QApplication.desktop()
        available_rect = desktop.availableGeometry(self)

        # Calculate base size (75% of available area)
        width = int(available_rect.width() * 0.75)
        height = int(available_rect.height() * 0.75)

        # Offset for cascading
        offset_x = 30
        offset_y = 30

        # Position the docks in a cascade
        for i, dock in enumerate(floating_docks):
            x = available_rect.x() + (i * offset_x)
            y = available_rect.y() + (i * offset_y)

            # Ensure we don't go off screen
            if x + width > available_rect.right():
                x = available_rect.x()

            if y + height > available_rect.bottom():
                y = available_rect.y()

            dock.setGeometry(x, y, width, height)

    @pyqtSlot()
    def _on_tab_docks(self):
        """Tab all dockable PDF viewers together."""
        # Get all PDF dock widgets
        dock_widgets = [dock for dock in self.findChildren(DockablePDFView)]

        if len(dock_widgets) < 2:
            return

        # Get the first dock widget as the base
        base_dock = dock_widgets[0]

        # Make sure it's not floating
        if base_dock.isFloating():
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, base_dock)

        # Tab all other dock widgets with the base
        for dock in dock_widgets[1:]:
            if dock.isFloating():
                self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

            self.tabifyDockWidget(base_dock, dock)

        # Activate the base dock to bring it to front
        base_dock.raise_()
    
    def _open_document(self, document_id):
        """Open a document in a new tab or dock widget."""
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return
        
        # Update last accessed time
        document.last_accessed = datetime.utcnow()
        self.db_session.commit()
        
        # Update the queue view with the current document
        if hasattr(self, 'queue_view'):
            self.queue_view.set_current_document(document_id)
        
        # Use the regular tab approach for all document types, including PDFs
        document_view = DocumentView(self.db_session, document_id)
        
        # Connect the extractCreated signal
        document_view.extractCreated.connect(self._on_extract_created)
        
        # Connect the navigate signal
        document_view.navigate.connect(self._on_document_navigation)
        
        # Add to tab widget
        tab_index = self.content_tabs.addTab(document_view, document.title)
        self.content_tabs.setCurrentIndex(tab_index)
    
    @pyqtSlot(str)
    def _on_document_navigation(self, direction):
        """Handle navigation between documents while closing the current tab."""
        # Get the current tab index
        current_index = self.content_tabs.currentIndex()
        
        # Save the current tab's widget to close it after opening the new document
        current_widget = self.content_tabs.currentWidget()
        
        # Determine which document to navigate to
        if direction == "next":
            # Navigate to the next document
            self._on_read_next()
        elif direction == "previous":
            # Navigate to the previous document
            self._on_prev_document()
        
        # Close the previous tab
        if current_widget:
            # Ensure the current widget gets its closeEvent called
            # which will save position and perform cleanup
            self._force_close_tab(current_index)
    
    @pyqtSlot()
    def _on_read_next(self):
        """Read the next document from the queue."""
        try:
            # Use the queue view's logic for finding the next document
            self.queue_view._on_read_next()
        except Exception as e:
            logger.exception(f"Error getting next document to read: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error retrieving next document: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_prev_document(self):
        """Navigate to the previous document in the queue."""
        try:
            # Use the queue view's logic for finding the previous document
            self.queue_view._on_read_prev()
        except Exception as e:
            logger.exception(f"Error getting previous document: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error retrieving previous document: {str(e)}"
            )
    
    def _open_extract(self, extract_id):
        """Open an extract in a new tab."""
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            logger.error(f"Extract not found: {extract_id}")
            return
        
        # Create extract view
        extract_view = ExtractView(extract, self.db_session)
        
        # Add to tab widget
        tab_title = f"Extract {extract_id}"
        if extract.document:
            tab_title += f" ({extract.document.title})"
            
        tab_index = self.content_tabs.addTab(extract_view, tab_title)
        self.content_tabs.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_new_learning_item(self):
        """Create a new learning item."""
        try:
            # Get current document if available
            document_id = self.get_current_document_id()
            extract_id = None
            
            if document_id:
                # Optionally create an extract first
                # Or just pass document info for reference
                pass
            
            # Create and show the editor with theme and settings
            editor = LearningItemEditor(
                self.db_session, 
                extract_id=extract_id,
                settings_manager=self.settings_manager,
                theme_manager=self.theme_manager
            )
            editor.itemSaved.connect(self._on_learning_item_saved)
            editor.exec()
            
        except Exception as e:
            logger.exception(f"Error creating learning item: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to open learning item editor: {str(e)}"
            )
    
    @pyqtSlot(int)
    def _on_edit_learning_item(self, item_id):
        """Edit an existing learning item."""
        try:
            # Create editor dialog and show it
            editor = LearningItemEditor(
                self.db_session, 
                item_id=item_id,
                settings_manager=self.settings_manager,
                theme_manager=self.theme_manager
            )
            editor.itemSaved.connect(self._on_learning_item_saved)
            editor.itemDeleted.connect(self._on_learning_item_deleted)
            editor.exec()
            
        except Exception as e:
            logger.exception(f"Error editing learning item: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to open learning item editor: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_manage_tags(self):
        """Open the tag manager dialog."""
        try:
            # Create and show the tag manager dialog
            from ui.tag_view import TagView
            
            # Create TagView with only db_session as required
            tag_view = TagView(self.db_session)
            
            # Add to a dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Tag Manager")
            dialog.setMinimumSize(800, 600)
            
            # Create layout
            layout = QVBoxLayout(dialog)
            layout.addWidget(tag_view)
            
            # Add close button at the bottom
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            close_button = QPushButton("Close")
            close_button.clicked.connect(dialog.accept)
            button_layout.addWidget(close_button)
            
            layout.addLayout(button_layout)
            
            # Show dialog
            dialog.exec()
            
        except Exception as e:
            logger.exception(f"Error opening tag manager: {e}")
            QMessageBox.critical(
                self, "Error",
                f"Error opening tag manager: {str(e)}"
            )
    
    @pyqtSlot(bool)
    def _on_toggle_category_panel(self, checked):
        """Handler for toggling category panel visibility."""
        # Since the left_pane no longer exists, we need to handle this differently
        # Update the category dock widget if it exists
        if hasattr(self, 'category_dock') and self.category_dock:
            if checked:
                self.category_dock.show()
            else:
                self.category_dock.hide()
        
        # Update setting
        self.settings_manager.set_setting("ui", "show_category_panel", checked)
        self.settings_manager.save_settings()
    
    @pyqtSlot(bool)
    def _on_toggle_search_panel(self, checked):
        """Handler for toggling search panel visibility."""
        if checked:
            self.search_dock.show()
        else:
            self.search_dock.hide()
    
    @pyqtSlot(bool)
    def _on_toggle_stats_panel(self, checked):
        """Handler for toggling statistics panel visibility."""
        if checked:
            self.stats_dock.show()
        else:
            self.stats_dock.hide()
    
    @pyqtSlot(bool)
    def _on_toggle_queue_panel(self, checked):
        """Toggle visibility of the queue panel."""
        if hasattr(self, 'queue_dock'):
            self.queue_dock.setVisible(checked)

    @pyqtSlot(bool)
    def _on_toggle_knowledge_tree(self, checked):
        """Toggle visibility of the knowledge tree panel."""
        try:
            # Find the queue view that contains the knowledge tree
            for index in range(self.content_tabs.count()):
                widget = self.content_tabs.widget(index)
                if hasattr(widget, 'tree_dock') and widget.tree_dock:
                    # If we found a widget with a tree dock, toggle its visibility
                    widget.tree_dock.setVisible(checked)
                    return
                    
            # If we didn't find a docked tree panel, look for the main queue view
            queue_view = self.findChild(QWidget, 'queue_view')
            if queue_view and hasattr(queue_view, '_make_tree_dockable'):
                # If the knowledge tree is not dockable yet, make it dockable first
                if not hasattr(queue_view, 'tree_dock') or not queue_view.tree_dock:
                    queue_view._make_tree_dockable()
                
                # Then set visibility based on checked state
                if hasattr(queue_view, 'tree_dock') and queue_view.tree_dock:
                    queue_view.tree_dock.setVisible(checked)
                else:
                    # Fall back to toggling tree panel in splitter mode
                    if hasattr(queue_view, 'tree_panel') and hasattr(queue_view, '_toggle_tree_panel'):
                        if checked and not queue_view.tree_panel.isVisible():
                            queue_view._toggle_tree_panel()
                        elif not checked and queue_view.tree_panel.isVisible():
                            queue_view._toggle_tree_panel()
        except Exception as e:
            logger.exception(f"Error toggling knowledge tree: {e}")

    @pyqtSlot(QModelIndex)
    def _on_category_selected(self, index):
        """Handler for category selection."""
        category_id = self.category_model.get_category_id(index)
        if category_id is not None:
            # Update document model to show documents in this category
            self.document_model.set_category_filter(category_id)
    
    @pyqtSlot(QPoint)
    def _on_category_context_menu(self, pos):
        """Show context menu for category tree."""
        index = self.category_tree.indexAt(pos)
        if not index.isValid():
            return
        
        category_id = self.category_model.get_category_id(index)
        category = self.db_session.query(Category).get(category_id)
        if not category:
            return
        
        menu = QMenu(self)
        
        # Add actions
        new_category_action = menu.addAction("New Subcategory")
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        
        # Connect actions
        new_category_action.triggered.connect(lambda: self._on_new_category(category_id))
        rename_action.triggered.connect(lambda: self._on_rename_category(category_id))
        delete_action.triggered.connect(lambda: self._on_delete_category(category_id))
        
        menu.exec(self.category_tree.viewport().mapToGlobal(pos))
    
    @pyqtSlot(int)
    def _on_new_category(self, parent_id):
        """Handler for creating a new category."""
        name, ok = QInputDialog.getText(
            self, "New Category", 
            "Enter category name:"
        )
        
        if ok and name:
            try:
                # Create category using the helper function
                from core.utils.category_helper import create_category
                create_category(self.db_session, name, parent_id)
                
                # Reload category model
                self.category_model._reload_categories()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to create category: {e}")
                QMessageBox.warning(self, "Error", f"Error creating category: {str(e)}")
    
    @pyqtSlot(int)
    def _on_rename_category(self, category_id):
        """Handler for renaming a category."""
        category = self.db_session.query(Category).get(category_id)
        if not category:
            return
        
        name, ok = QInputDialog.getText(
            self, "Rename Category", 
            "Enter new name:",
            text=category.name
        )
        
        if ok and name:
            try:
                # Rename category using the helper function
                from core.utils.category_helper import rename_category
                rename_category(self.db_session, category_id, name)
                
                # Reload category model
                self.category_model._reload_categories()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to rename category: {e}")
                QMessageBox.warning(self, "Error", f"Error renaming category: {str(e)}")
    
    @pyqtSlot(int)
    def _on_delete_category(self, category_id):
        """Handler for deleting a category."""
        category = self.db_session.query(Category).get(category_id)
        if not category:
            return
        
        try:
            # Check for child categories
            children_count = self.db_session.query(Category).filter(Category.parent_id == category_id).count()
            
            # Check for documents
            from core.knowledge_base.models import Document
            documents_count = self.db_session.query(Document).filter(Document.category_id == category_id).count()
            
            # Build confirmation message
            msg = f"Are you sure you want to delete the category '{category.name}'?"
            
            if children_count > 0:
                msg += f"\n\nThis will also delete {children_count} subcategories."
                
            if documents_count > 0:
                msg += f"\n\nThis will remove the category from {documents_count} documents."
            
            # Confirm deletion
            reply = QMessageBox.question(
                self, "Confirm Delete", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Delete category using the helper function
                from core.utils.category_helper import delete_category
                delete_category(self.db_session, category_id, force=True)
                
                # Reload category model
                self.category_model._reload_categories()
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to delete category: {e}")
            QMessageBox.warning(self, "Error", f"Error deleting category: {str(e)}")
    
    @pyqtSlot(QModelIndex)
    def _on_document_activated(self, index):
        """Handler for document activation (double-click)."""
        document_id = self.document_model.get_document_id(index)
        if document_id is not None:
            self._open_document(document_id)
    
    @pyqtSlot(QPoint)
    def _on_document_context_menu(self, pos):
        """Show context menu for document list."""
        index = self.document_list.indexAt(pos)
        if not index.isValid():
            return
        
        document_id = self.document_model.get_document_id(index)
        document = self.db_session.query(Document).get(document_id)
        if not document:
            return
        
        menu = QMenu(self)
        
        # Add actions
        open_action = menu.addAction("Open")
        open_action.triggered.connect(lambda: self._open_document(document_id))
        
        menu.addSeparator()
        
        summarize_action = menu.addAction("Summarize...")
        summarize_action.triggered.connect(lambda: self._show_document_summary(document_id))
        
        edit_tags_action = menu.addAction("Edit Tags...")
        edit_tags_action.triggered.connect(lambda: self._on_edit_document_tags(document_id))
        
        change_category_action = menu.addAction("Change Category")
        change_category_action.triggered.connect(lambda: self._on_change_document_category(document_id))
        
        delete_action = menu.addAction("Delete")
        
        # Connect actions
        edit_tags_action.triggered.connect(lambda: self._on_edit_document_tags(document_id))
        change_category_action.triggered.connect(lambda: self._on_change_document_category(document_id))
        delete_action.triggered.connect(lambda: self._on_delete_document(document_id))
        
        menu.exec(self.document_list.viewport().mapToGlobal(pos))
    
    @pyqtSlot(int)
    def _on_edit_document_tags(self, document_id):
        """Handler for editing document tags."""
        document = self.db_session.query(Document).get(document_id)
        if not document:
            return
        
        # Get current tags
        current_tags = [tag.name for tag in document.tags]
        
        # Get tag input
        tags_str, ok = QInputDialog.getText(
            self, "Edit Tags", 
            "Enter tags (comma-separated):",
            text=", ".join(current_tags)
        )
        
        if ok:
            # Clear existing tags
            document.tags = []
            
            # Add new tags
            if tags_str:
                for tag_name in [t.strip() for t in tags_str.split(',') if t.strip()]:
                    self.tag_manager.add_document_tag(document_id, tag_name)
    
    @pyqtSlot(int)
    def _on_change_document_category(self, document_id):
        """Handler for changing document category."""
        document = self.db_session.query(Document).get(document_id)
        if not document:
            return
        
        # Get categories
        categories = self.db_session.query(Category).order_by(Category.name).all()
        category_names = ["(None)"] + [cat.name for cat in categories]
        
        # Get current category
        current_index = 0
        if document.category_id:
            for i, cat in enumerate(categories, 1):
                if cat.id == document.category_id:
                    current_index = i
                    break
        
        # Show selection dialog
        category_name, ok = QInputDialog.getItem(
            self, "Change Category", 
            "Select category:",
            category_names, current_index, False
        )
        
        if ok:
            # Update category
            if category_name == "(None)":
                document.category_id = None
            else:
                category = next((cat for cat in categories if cat.name == category_name), None)
                if category:
                    document.category_id = category.id
            
            self.db_session.commit()
            
            # Reload document list
            self.document_model._reload_documents()
    
    @pyqtSlot(int)
    def _on_delete_document(self, document_id):
        """Handler for deleting a document."""
        document = self.db_session.query(Document).get(document_id)
        if not document:
            return
        
        # Count extracts and learning items
        extract_count = self.db_session.query(Extract).filter(Extract.document_id == document_id).count()
        
        # Confirmation
        msg = f"Are you sure you want to delete document '{document.title}'?"
        
        if extract_count > 0:
            msg += f"\n\nThis will also delete {extract_count} extracts and all associated learning items."
        
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Delete document
            self.db_session.delete(document)
            self.db_session.commit()
            
            # Reload document list
            self.document_model._reload_documents()
    
    def eventFilter(self, obj, event):
        """Filter events to handle middle mouse clicks on tabs."""
        if obj == self.content_tabs and event.type() == event.Type.MouseButtonRelease:
            # Check if it's a middle mouse button click
            if event.button() == Qt.MouseButton.MiddleButton:
                # Find the tab under the cursor
                tab_bar = self.content_tabs.tabBar()
                tab_index = tab_bar.tabAt(event.pos())
                
                if tab_index != -1:  # Valid tab index
                    logger.debug(f"Middle-click detected on tab {tab_index}")
                    # Close tab without rating
                    self._force_close_tab(tab_index)
                    return True  # Event handled
        
        # Pass other events to default handler
        return super().eventFilter(obj, event)
    
    def _force_close_tab(self, index):
        """Close tab without prompting for rating."""
        widget = self.content_tabs.widget(index)
        
        # Check if widget is a document view
        if isinstance(widget, DocumentView):
            # Save document position
            if hasattr(widget, '_save_position'):
                widget._save_position()
        
        # Remove tab without rating prompt
        self.content_tabs.removeTab(index)
        widget.deleteLater()
        
        # Update the session state
        self._save_session()
    
    @pyqtSlot(int)
    def _on_tab_close_requested(self, index):
        """Handle tab close request."""
        widget = self.content_tabs.widget(index)
        
        # Check if widget is a document view
        if isinstance(widget, DocumentView):
            # Save document position
            if hasattr(widget, '_save_position'):
                widget._save_position()
                
            # Get document ID
            document_id = widget.document.id
            
            # Prompt for rating if this is a document
            self._prompt_document_rating(document_id)
        
        # Remove tab
        self.content_tabs.removeTab(index)
        widget.deleteLater()
        
        # Update the session state
        self._save_session()

    def _prompt_document_rating(self, document_id):
        """Prompt the user to rate a document for scheduling."""
        # Get document
        document = self.db_session.query(Document).get(document_id)
        if not document:
            return
        
        # Create rating dialog
        rating_dialog = QDialog(self)
        rating_dialog.setWindowTitle(f"Rate Document: {document.title}")
        rating_dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(rating_dialog)
        
        # Instruction label
        label = QLabel(
            f"How difficult was this document to understand?\n"
            f"This will schedule it for future review."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        
        # Rating buttons
        rating_layout = QHBoxLayout()
        
        ratings = [
            ("Hard/Forgot (1)", 1),
            ("Difficult (2)", 2),
            ("Good (3)", 3),
            ("Easy (4)", 4),
            ("Very Easy (5)", 5)
        ]
        
        for text, value in ratings:
            button = QPushButton(text)
            button.clicked.connect(lambda checked, r=value: self._on_document_rated(document_id, r, rating_dialog))
            rating_layout.addWidget(button)
        
        layout.addLayout(rating_layout)
        
        # Skip button
        skip_layout = QHBoxLayout()
        skip_layout.addStretch()
        
        skip_button = QPushButton("Skip Rating")
        skip_button.clicked.connect(rating_dialog.reject)
        skip_layout.addWidget(skip_button)
        
        layout.addLayout(skip_layout)
        
        # Show dialog
        rating_dialog.exec()
    
    def _on_document_rated(self, document_id, rating, dialog):
        """Handle document rating."""
        # Schedule document
        result = self.queue_manager.schedule_document(document_id, rating)
        
        if result:
            # Show scheduling info
            QMessageBox.information(
                self, "Document Scheduled", 
                f"Document rated as {rating}/5.\n"
                f"Next review scheduled for {result['next_reading_date'].strftime('%Y-%m-%d')}."
            )
        else:
            QMessageBox.warning(
                self, "Error", 
                f"Failed to schedule document."
            )
        
        # Close dialog
        dialog.accept()
    
    @pyqtSlot()
    def _on_start_review(self):
        """Handler for starting a review session."""
        # Get due items
        items = self.spaced_repetition.get_due_items(limit=50)
        
        if not items:
            QMessageBox.information(
                self, "No Items Due", 
                "There are no items due for review."
            )
            return
        
        # Create review view
        review_view = ReviewView(items, self.spaced_repetition, self.db_session)
        
        # Add to tab widget
        tab_index = self.content_tabs.addTab(review_view, "Review Session")
        self.content_tabs.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_browse_extracts(self):
        """Handler for browsing extracts."""
        # Use search with extract filter
        self.search_dock.show()
        self.action_toggle_search_panel.setChecked(True)
        
        # Set entity type to extracts
        self.search_view.entity_type_combo.setCurrentIndex(2)  # "Extracts" option
        
        # Trigger search
        self.search_view._on_search()
    
    
    
    @pyqtSlot()
    def _on_browse_learning_items(self):
        """Handler for browsing learning items."""
        # Use search with learning items filter
        self.search_dock.show()
        self.action_toggle_search_panel.setChecked(True)
        
        # Set entity type to learning items
        self.search_view.entity_type_combo.setCurrentIndex(3)  # "Learning Items" option
        
        # Trigger search
        self.search_view._on_search()
    
    @pyqtSlot()
    def _on_search(self):
        """Handler for search action."""
        self.search_dock.show()
        self.action_toggle_search_panel.setChecked(True)
        
        # Focus search box
        self.search_view.search_box.setFocus()
    
    @pyqtSlot(str, int)
    def _on_search_item_selected(self, item_type, item_id):
        """Handler for search item selection."""
        if item_type == "document":
            self._open_document(item_id)
        elif item_type == "extract":
            self._open_extract(item_id)
        elif item_type == "learning_item":
            self._open_learning_item(item_id)
    
    @pyqtSlot()
    def _on_view_network(self):
        """Handler for viewing knowledge network."""
        # Create network view
        network_view = NetworkView(self.db_session)
        
        # Add to tab widget
        tab_index = self.content_tabs.addTab(network_view, "Knowledge Network")
        self.content_tabs.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_backup_restore(self):
        """Handler for backup and restore."""
        # Create backup view
        backup_view = BackupView(self.db_session)
        
        # Add to tab widget
        tab_index = self.content_tabs.addTab(backup_view, "Backup & Restore")
        self.content_tabs.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_show_settings(self):
        """Handler for showing settings dialog."""
        dialog = SettingsDialog(self.settings_manager, self)
        dialog.settingsChanged.connect(self._on_settings_changed)
        dialog.exec()
    
    @pyqtSlot()
    def _on_settings_changed(self):
        """Handler for settings changes."""
        # Apply settings
        self._apply_settings()
        
        # Update auto-save timer
        interval_minutes = self.settings_manager.get_setting("general", "auto_save_interval", 5)
        interval_ms = interval_minutes * 60 * 1000
        self.auto_save_timer.start(interval_ms)
        
        # Update FSRS parameters in queue view
        if hasattr(self, 'queue_view'):
            self.queue_view.update_settings()
    
    @pyqtSlot()
    def _on_show_statistics(self):
        """Handler for showing statistics dashboard."""
        self.stats_dock.show()
        self.action_toggle_stats_panel.setChecked(True)
        
        # Create statistics view in tab
        stats_view = StatisticsWidget(self.db_session)
        
        # Add to tab widget
        tab_index = self.content_tabs.addTab(stats_view, "Statistics")
        self.content_tabs.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_recent_document_selected(self):
        """Handler for selecting a document from the recent menu."""
        action = self.sender()
        if action:
            document_id = action.data()
            self._open_document(document_id)
    
    @pyqtSlot(int)
    def _on_extract_created(self, extract_id):
        """Handler for extract creation."""
        # Open extract view
        self._open_extract(extract_id)
        
        # Auto suggest tags if enabled
        auto_suggest = self.settings_manager.get_setting("document", "auto_suggest_tags", True)
        if auto_suggest:
            suggested_tags = self.tag_manager.suggest_tags_for_extract(extract_id)
            
            if suggested_tags:
                # Add tags automatically
                for tag in suggested_tags:
                    self.tag_manager.add_extract_tag(extract_id, tag)
    
    @pyqtSlot(int)
    def _on_learning_item_saved(self, item_id):
        """Handler for learning item save."""
        # Update status
        self._update_status()
    
    @pyqtSlot(int)
    def _on_learning_item_deleted(self, item_id):
        """Handler for learning item deletion."""
        # Update status
        self._update_status()
        
        # Close tab
        current_index = self.content_tabs.currentIndex()
        self.content_tabs.removeTab(current_index)
    
    @pyqtSlot()
    def _on_about(self):
        """Handler for about action."""
        about_text = """
        <h1>Incrementum</h1>
        <p>Advanced Incremental Learning System</p>
        <p>Version 1.0</p>
        <p>An application for efficient knowledge management and spaced repetition.</p>
        <p>Features:</p>
        <ul>
            <li>Document import and processing</li>
            <li>Knowledge extraction with NLP</li>
            <li>Spaced repetition with SM-18 algorithm</li>
            <li>Knowledge network visualization</li>
            <li>Advanced search and tagging</li>
            <li>Customizable interface layout</li>
        </ul>
        
        <h3>Customizing Your Layout</h3>
        <p>You can customize the interface layout to suit your workflow:</p>
        <ul>
            <li>Drag any panel (Categories, Queue, Search, etc.) by its title bar to move it to a different position</li>
            <li>Drag to the left, right, top, or bottom edge of the window to dock in that position</li>
            <li>Drag to the center of another panel to create tabs</li>
            <li>Double-click a panel's title bar to float it as a separate window</li>
        </ul>
        <p>Use the <b>View > Layout Management</b> menu to save your custom layout or restore defaults.</p>
        """
        
        QMessageBox.about(self, "About Incrementum", about_text)
    
    @pyqtSlot()
    def _on_view_queue(self):
        """Handler for viewing the reading queue."""
        # Show the queue dock
        self.queue_dock.show()
        self.action_toggle_queue_panel.setChecked(True)
        
        # Focus the queue widget
        self.queue_view.setFocus()
    
    @pyqtSlot()
    def _on_import_arxiv(self):
        """Handler for importing from ArXiv."""
        # Create dialog
        arxiv_dialog = ArxivDialog(self.document_processor, self.db_session, self)
        
        # Show dialog
        if arxiv_dialog.exec():
            # Dialog will handle the import directly
            self._load_recent_documents()
            self._update_status()

    @pyqtSlot()
    def _on_layout_help(self):
        """Show help about interface layout customization."""
        layout_help_text = """
        <h2>Customizing Your Interface Layout</h2>
        
        <p>Incrementum offers a fully customizable interface to suit your workflow. You can arrange 
        panels in any configuration you prefer, including moving the reading view to the center.</p>
        
        <h3>Moving Panels</h3>
        <ul>
            <li><b>Drag and Drop:</b> Click and drag a panel's title bar to move it</li>
            <li><b>Dock Position:</b> Drag to any edge of the window (left, right, top, bottom) to dock it there</li>
            <li><b>Center Reading View:</b> Move side panels away from the center to give the reading view more space</li>
            <li><b>Create Tabs:</b> Drag a panel onto another panel to create tabbed interfaces</li>
            <li><b>Floating Windows:</b> Double-click a panel's title bar to detach it as a floating window</li>
        </ul>
        
        <h3>Layout Management</h3>
        <p>Use the <b>View > Layout Management</b> menu to:</p>
        <ul>
            <li><b>Save Current Layout:</b> Save your current panel arrangement</li>
            <li><b>Load Saved Layout:</b> Restore your saved panel arrangement</li>
            <li><b>Reset to Default Layout:</b> Return to the default panel arrangement</li>
        </ul>
        
        <p>Your saved layout will be automatically restored when you restart the application.</p>
        """
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Interface Layout Help")
        msg_box.setText(layout_help_text)
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.exec()

    @pyqtSlot()
    def _on_open_web_browser(self):
        """Open the web browser view."""
        # Check if web browsing is enabled in settings
        if not self.settings_manager.get_setting("ui", "web_browser_enabled", True):
            QMessageBox.information(
                self, "Web Browser Disabled", 
                "Web browsing is disabled in settings. Please enable it in Settings > User Interface."
            )
            return

        try:
            # Create new web browser view
            browser_view = WebBrowserView(self.db_session)
            
            # Connect extract created signal
            browser_view.extractCreated.connect(self._on_extract_created)
            
            # Add to tab widget
            tab_index = self.content_tabs.addTab(browser_view, "Web Browser")
            self.content_tabs.setCurrentIndex(tab_index)
            
            # Update status
            self.status_label.setText("Web browser opened")
            
        except ImportError as e:
            QMessageBox.warning(
                self, "Web Browser Error", 
                f"Could not open web browser: {str(e)}\n\nWeb browsing requires QtWebEngine which may not be installed."
            )
        except Exception as e:
            QMessageBox.warning(
                self, "Web Browser Error", 
                f"Error opening web browser: {str(e)}"
            )

    def get_current_document_id(self):
        """
        Get the ID of the currently active document.
        
        Returns:
            int or None: The ID of the current document, or None if no document is open.
        """
        if self.mdi_area.activeSubWindow():
            widget = self.mdi_area.activeSubWindow().widget()
            if hasattr(widget, 'document_id'):
                return widget.document_id
        return None

    @pyqtSlot()
    def _on_export_all_data(self):
        """Handler for exporting all data."""
        from ui.export_dialog import ExportDialog
        
        # Create dialog with no pre-selected extracts or items
        dialog = ExportDialog(self.db_session, None, None, self)
        
        # Pre-select "All Data" option (it should already be the default when no IDs are provided)
        if hasattr(dialog, 'all_data_radio'):
            dialog.all_data_radio.setChecked(True)
            dialog._on_export_type_changed()  # Update UI based on selection
        
        # Show dialog
        dialog.exec()

    def _create_menus(self):
        """Create and return menu bar with menus."""
        # Use existing menubar instead of creating a new one
        # menubar = QMenuBar()  <- This is the problem!
        
        # Clear existing menus first to avoid duplicates
        self.file_menu.clear()
        self.edit_menu.clear()
        self.view_menu.clear()
        self.learning_menu.clear()
        self.tools_menu.clear()
        self.help_menu.clear()
        
        # Recreate theme menu
        self.theme_menu = self.view_menu.addMenu("Themes")
        self._setup_theme_menu()
        
        # File menu
        # Add arxiv import action
        self.action_import_arxiv = QAction("Import from Arxiv...", self)
        self.action_import_arxiv.triggered.connect(self._on_import_arxiv)
        self.file_menu.addAction(self.action_import_arxiv)
        
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.action_import_knowledge)
        self.file_menu.addAction(self.action_export_knowledge)
        
        # Add export all data action
        self.action_export_all_data = QAction("Export All Data...", self)
        self.action_export_all_data.triggered.connect(self._on_export_all_data)
        self.file_menu.addAction(self.action_export_all_data)
        
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.action_save)
        self.file_menu.addSeparator()
        
        # Recent documents submenu
        self.recent_menu = QMenu("Recent Documents", self)
        self.file_menu.addMenu(self.recent_menu)
        
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.action_exit)
        
        # Edit menu
        self.edit_menu.addAction(self.action_new_extract)
        self.edit_menu.addAction(self.action_new_learning_item)
        self.edit_menu.addSeparator()
        self.edit_menu.addAction(self.action_manage_tags)
        
        # View menu - Panel toggles
        panels_menu = self.view_menu.addMenu("Panels")
        panels_menu.addAction(self.action_toggle_toolbar)  # Add toolbar toggle
        panels_menu.addAction(self.action_toggle_category_panel)
        panels_menu.addAction(self.action_toggle_search_panel)
        panels_menu.addAction(self.action_toggle_stats_panel)
        panels_menu.addAction(self.action_toggle_queue_panel)
        panels_menu.addAction(self.action_toggle_knowledge_tree)
        
        # Add dock arrangement actions
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.action_tile_docks)
        self.view_menu.addAction(self.action_cascade_docks)
        self.view_menu.addAction(self.action_tab_docks)
        
        # Learning menu
        self.learning_menu.addAction(self.action_start_review)
        self.learning_menu.addSeparator()
        self.learning_menu.addAction(self.action_browse_extracts)
        self.learning_menu.addAction(self.action_browse_learning_items)
        
        # Tools menu
        self.tools_menu.addAction(self.action_start_review)
        self.tools_menu.addAction(self.action_view_queue)
        self.tools_menu.addAction(self.action_prev_document)
        self.tools_menu.addAction(self.action_read_next)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.action_search)
        self.tools_menu.addAction(self.action_view_network)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.action_backup_restore)
        self.tools_menu.addAction(self.action_settings)
        self.tools_menu.addAction(self.action_statistics)
        self.tools_menu.addAction(self.action_summarize_document)
        
        # RSS and YouTube
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.action_rss_feeds)
        self.tools_menu.addAction(self.action_youtube_playlists)  # Add YouTube Playlists action
        
        # Other tools
        self.tools_menu.addAction(self.action_tag_manager)
        self.tools_menu.addAction(self.action_batch_processor)
        self.tools_menu.addAction(self.action_review_manager)
        self.tools_menu.addAction(self.action_backup)
        
        # Help menu
        help_action = QAction("Documentation", self)
        help_action.triggered.connect(self._on_show_documentation)
        self.help_menu.addAction(help_action)
        
        layout_help_action = QAction("Interface Layout", self)
        layout_help_action.triggered.connect(self._on_layout_help)
        self.help_menu.addAction(layout_help_action)
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._on_about)
        self.help_menu.addAction(about_action)

    @pyqtSlot()
    def _on_show_documentation(self):
        """Show documentation by displaying markdown files."""
        try:
            import os
            
            # Try to import markdown, but handle the case where it's not installed
            try:
                import markdown
                markdown_available = True
            except ImportError:
                markdown_available = False
                logger.warning("Markdown module not installed. Documentation will be displayed as plain text.")
                # Show warning to user
                QMessageBox.warning(
                    self, "Module Missing",
                    "The 'markdown' Python package is not installed. Documentation will be displayed as plain text.\n\n"
                    "To install it, run: pip install markdown"
                )
            
            # Create documentation dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Incrementum Documentation")
            dialog.resize(900, 700)
            
            # Create layout
            layout = QVBoxLayout(dialog)
            
            # Create tab widget to organize documentation
            tab_widget = QTabWidget()
            
            # Find all markdown files in docs directory
            docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
            
            if os.path.exists(docs_dir):
                # Create a tab for main documentation files
                main_docs_tab = QWidget()
                main_docs_layout = QVBoxLayout(main_docs_tab)
                
                # Create a list of available documentation
                docs_list = QListWidget()
                main_docs_layout.addWidget(QLabel("<h2>Available Documentation</h2>"))
                main_docs_layout.addWidget(docs_list)
                
                # Content display
                docs_content = QTextEdit()
                docs_content.setReadOnly(True)
                main_docs_layout.addWidget(docs_content)
                
                # Add to tabs
                tab_widget.addTab(main_docs_tab, "Main Documentation")
                
                # Populate list with markdown files
                main_md_files = [f for f in os.listdir(docs_dir) if f.endswith('.md')]
                
                for md_file in sorted(main_md_files):
                    docs_list.addItem(md_file)
                
                # Connect selection signal
                docs_list.currentItemChanged.connect(
                    lambda current, previous: self._display_markdown_file(
                        os.path.join(docs_dir, current.text()), docs_content, markdown_available
                    ) if current else None
                )
                
                # Check for user guide directory
                user_guide_dir = os.path.join(docs_dir, "user_guide")
                if os.path.exists(user_guide_dir) and os.path.isdir(user_guide_dir):
                    self._add_documentation_tab(tab_widget, user_guide_dir, "User Guide", markdown_available)
                
                # Check for developer guide directory
                dev_guide_dir = os.path.join(docs_dir, "developer")
                if os.path.exists(dev_guide_dir) and os.path.isdir(dev_guide_dir):
                    self._add_documentation_tab(tab_widget, dev_guide_dir, "Developer Guide", markdown_available)
                
                # Select first item if available
                if docs_list.count() > 0:
                    docs_list.setCurrentRow(0)
            else:
                # No documentation found
                no_docs_label = QLabel("No documentation files found.")
                tab_widget.addTab(no_docs_label, "Documentation")
            
            # Add tab widget to layout
            layout.addWidget(tab_widget)
            
            # Add close button
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            close_button = QPushButton("Close")
            close_button.clicked.connect(dialog.accept)
            button_layout.addWidget(close_button)
            
            layout.addLayout(button_layout)
            
            # Show dialog
            dialog.exec()
            
        except Exception as e:
            logger.exception(f"Error showing documentation: {e}")
            QMessageBox.critical(
                self, "Error",
                f"Error showing documentation: {str(e)}"
            )
    
    def _add_documentation_tab(self, tab_widget, docs_dir, tab_title, markdown_available=True):
        """Add a tab for a documentation directory."""
        try:
            import os
            
            # Create tab and layout
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            
            # Create a list of available documentation
            docs_list = QListWidget()
            tab_layout.addWidget(QLabel(f"<h2>{tab_title} Documentation</h2>"))
            tab_layout.addWidget(docs_list)
            
            # Content display
            docs_content = QTextEdit()
            docs_content.setReadOnly(True)
            tab_layout.addWidget(docs_content)
            
            # Add to tabs
            tab_widget.addTab(tab, tab_title)
            
            # Populate list with markdown files
            md_files = [f for f in os.listdir(docs_dir) if f.endswith('.md')]
            
            for md_file in sorted(md_files):
                docs_list.addItem(md_file)
            
            # Connect selection signal
            docs_list.currentItemChanged.connect(
                lambda current, previous: self._display_markdown_file(
                    os.path.join(docs_dir, current.text()), docs_content, markdown_available
                ) if current else None
            )
            
            # Select first item if available
            if docs_list.count() > 0:
                docs_list.setCurrentRow(0)
                
        except Exception as e:
            logger.warning(f"Error adding documentation tab: {e}")
            
    def _display_markdown_file(self, file_path, text_edit, markdown_available=True):
        """Load and display a markdown file in the text edit widget."""
        try:
            import os
            
            # Check if file exists
            if not os.path.exists(file_path):
                text_edit.setHtml(f"<p>Error: File not found: {file_path}</p>")
                return
                
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                md_content = f.read()
            
            # If markdown is available, convert to HTML
            if markdown_available:
                try:
                    import markdown
                    # Convert markdown to HTML
                    html_content = markdown.markdown(
                        md_content, 
                        extensions=['extra', 'codehilite', 'toc', 'smarty']
                    )
                    
                    # Add CSS styling
                    styled_html = f"""
                    <html>
                    <head>
                        <style>
                            body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; }}
                            h1, h2, h3, h4 {{ color: #2c3e50; }}
                            h1 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; }}
                            h2 {{ border-bottom: 1px solid #eee; padding-bottom: 5px; }}
                            code {{ background-color: #f8f8f8; padding: 2px 4px; border-radius: 3px; }}
                            pre {{ background-color: #f8f8f8; padding: 10px; border-radius: 3px; overflow-x: auto; }}
                            blockquote {{ background-color: #f9f9f9; border-left: 4px solid #ccc; padding: 10px; margin: 10px 0; }}
                            img {{ max-width: 100%; }}
                            table {{ border-collapse: collapse; width: 100%; }}
                            th, td {{ border: 1px solid #ddd; padding: 8px; }}
                            tr:nth-child(even) {{ background-color: #f2f2f2; }}
                            th {{ padding-top: 12px; padding-bottom: 12px; text-align: left; background-color: #4CAF50; color: white; }}
                        </style>
                    </head>
                    <body>
                        {html_content}
                    </body>
                    </html>
                    """
                    
                    # Set HTML content in text edit
                    text_edit.setHtml(styled_html)
                    
                    # Set base URL for images and links
                    from PyQt6.QtCore import QUrl
                    base_url = QUrl.fromLocalFile(os.path.dirname(file_path) + os.path.sep)
                    text_edit.document().setBaseUrl(base_url)
                except Exception as e:
                    logger.warning(f"Error converting markdown: {e}")
                    # Fallback to plain text
                    text_edit.setPlainText(md_content)
            else:
                # Display as plain text with a simple header
                text_edit.setHtml(f"<h2>{os.path.basename(file_path)}</h2><pre>{md_content}</pre>")
            
        except Exception as e:
            logger.exception(f"Error displaying markdown file: {e}")
            text_edit.setHtml(f"<p>Error displaying file: {str(e)}</p>")

    @pyqtSlot()
    def _on_save_as(self):
        """Save the current document with a new name or location."""
        try:
            # Get the current document widget
            current_widget = self.content_tabs.currentWidget()
            
            # Check if there's an active document
            if not current_widget or not hasattr(current_widget, 'document_id'):
                QMessageBox.warning(self, "Save As", "No document is currently open.")
                return
                
            document_id = current_widget.document_id
            
            # Get document from database
            document = self.db_session.query(Document).get(document_id)
            if not document:
                QMessageBox.warning(self, "Error", "Document not found in database.")
                return
                
            # Ask for new file name and location
            options = QFileDialog.Options()
            default_name = document.title if document.title else "Document"
            
            # Get appropriate extension based on document type
            if hasattr(document, 'mime_type'):
                if 'pdf' in document.mime_type.lower():
                    default_name += ".pdf"
                    file_filter = "PDF Files (*.pdf);;All Files (*)"
                elif 'word' in document.mime_type.lower() or 'docx' in document.mime_type.lower():
                    default_name += ".docx"
                    file_filter = "Word Documents (*.docx);;All Files (*)"
                elif 'html' in document.mime_type.lower():
                    default_name += ".html"
                    file_filter = "HTML Files (*.html *.htm);;All Files (*)"
                elif 'text' in document.mime_type.lower():
                    default_name += ".txt"
                    file_filter = "Text Files (*.txt);;All Files (*)"
                else:
                    default_name += ".txt"
                    file_filter = "All Files (*)"
            else:
                default_name += ".txt"
                file_filter = "All Files (*)"
            
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Document As", default_name, file_filter, options=options
            )
            
            if not file_path:
                return  # User canceled
                
            # Copy document content to the new file
            if hasattr(document, 'file_path') and document.file_path and os.path.exists(document.file_path):
                # If original file exists, copy it
                try:
                    shutil.copy2(document.file_path, file_path)
                    QMessageBox.information(self, "Save As", f"Document saved as '{file_path}'")
                    
                    # Add to recent files
                    self._add_to_recent_files(file_path)
                    
                except Exception as e:
                    logger.exception(f"Error copying document: {e}")
                    QMessageBox.warning(self, "Error", f"Could not save document: {str(e)}")
            else:
                # If no original file, try to save content from database
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        content = document.content if hasattr(document, 'content') and document.content else ""
                        f.write(content)
                    QMessageBox.information(self, "Save As", f"Document saved as '{file_path}'")
                    
                    # Add to recent files
                    self._add_to_recent_files(file_path)
                    
                except Exception as e:
                    logger.exception(f"Error saving document content: {e}")
                    QMessageBox.warning(self, "Error", f"Could not save document content: {str(e)}")
        
        except Exception as e:
            logger.exception(f"Error in Save As operation: {e}")
            QMessageBox.warning(self, "Error", f"An error occurred: {str(e)}")

    @pyqtSlot()
    def _on_export_pdf(self):
        """Export the current document as PDF."""
        try:
            # Get the current document widget
            current_widget = self.content_tabs.currentWidget()
            
            # Check if there's an active document
            if not current_widget:
                QMessageBox.warning(self, "Export PDF", "No document is currently open.")
                return
                
            # If widget has built-in PDF export
            if hasattr(current_widget, 'export_pdf'):
                current_widget.export_pdf()
                return
                
            # Otherwise, use Qt's printing system to generate PDF
            from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
            
            # Create printer with PDF output
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            
            # Set default PDF name based on document title if available
            if hasattr(current_widget, 'document_id'):
                document_id = current_widget.document_id
                document = self.db_session.query(Document).get(document_id)
                if document and document.title:
                    default_name = f"{document.title}.pdf"
                else:
                    default_name = "document.pdf"
                
                printer.setOutputFileName(default_name)
            
            # Show print dialog for PDF settings
            dialog = QPrintDialog(printer, self)
            dialog.setWindowTitle("Export to PDF")
            
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return  # User canceled
                
            # Attempt to print to PDF based on widget type
            success = False
            
            if hasattr(current_widget, 'print_'):
                # Direct print method
                current_widget.print_(printer)
                success = True
            elif hasattr(current_widget, 'document'):
                # Check if document is a method or a property
                doc = current_widget.document
                if callable(doc):
                    # It's a method, call it to get the document
                    doc = doc()
                
                # Check if the document has a print method
                if hasattr(doc, 'print') and callable(doc.print):
                    doc.print(printer)
                    success = True
            elif hasattr(current_widget, 'page') and hasattr(current_widget.page(), 'print'):
                # QWebEngineView
                def handle_print_finished(print_success):
                    if print_success:
                        QMessageBox.information(self, "Export PDF", f"Document exported to PDF: {printer.outputFileName()}")
                        self._add_to_recent_files(printer.outputFileName())
                    else:
                        QMessageBox.warning(self, "Export PDF", "Failed to export document to PDF.")
                
                current_widget.page().print(printer, handle_print_finished)
                return  # Async operation, return immediately
                
            if success:
                QMessageBox.information(self, "Export PDF", f"Document exported to PDF: {printer.outputFileName()}")
                self._add_to_recent_files(printer.outputFileName())
            else:
                QMessageBox.warning(self, "Export PDF", "This document type doesn't support PDF export.")
        
        except Exception as e:
            logger.exception(f"Error exporting to PDF: {e}")
            QMessageBox.warning(self, "Error", f"Failed to export PDF: {str(e)}")

    def _update_recent_files_menu(self):
        """Update the Recent Files menu with the list of recent files."""
        try:
            # Clear the menu
            self.recent_files_menu.clear()
            
            # Get recent files from settings
            recent_files = self.settings_manager.get_setting("ui", "recent_files", [])
            
            if recent_files:
                # Add recent file entries
                for file_path in recent_files:
                    if os.path.exists(file_path):
                        # Create a shorter display name
                        display_name = os.path.basename(file_path)
                        
                        # Create action with the file path as data
                        action = QAction(display_name, self)
                        action.setToolTip(file_path)
                        action.setData(file_path)
                        action.triggered.connect(self._on_recent_file_selected)
                        self.recent_files_menu.addAction(action)
                
                # Add separator and clear action
                self.recent_files_menu.addSeparator()
                self.recent_files_menu.addAction(self.action_clear_recent)
            else:
                # Add a disabled "No Recent Files" entry
                action = QAction("No Recent Files", self)
                action.setEnabled(False)
                self.recent_files_menu.addAction(action)
                self.recent_files_menu.addSeparator()
                self.recent_files_menu.addAction(self.action_clear_recent)
                self.action_clear_recent.setEnabled(False)
    
        except Exception as e:
            logger.exception(f"Error updating recent files menu: {e}")

    def _add_to_recent_files(self, file_path):
        """Add a file to the recent files list."""
        try:
            # Get current list
            recent_files = self.settings_manager.get_setting("ui", "recent_files", [])
            
            # Remove if already in list
            if file_path in recent_files:
                recent_files.remove(file_path)
            
            # Add to beginning of list
            recent_files.insert(0, file_path)
            
            # Limit to 10 entries
            recent_files = recent_files[:10]
            
            # Save updated list
            self.settings_manager.set_setting("ui", "recent_files", recent_files)
            
            # Update menu
            self._update_recent_files_menu()
        
        except Exception as e:
            logger.exception(f"Error adding to recent files: {e}")

    @pyqtSlot()
    def _on_recent_file_selected(self):
        """Handle selection of a file from the Recent Files menu."""
        try:
            action = self.sender()
            if action and action.data():
                file_path = action.data()
                
                if not os.path.exists(file_path):
                    QMessageBox.warning(self, "File Not Found", f"The file '{file_path}' no longer exists.")
                    # Remove from recent files
                    self._remove_from_recent_files(file_path)
                    return
                    
                # Import the file
                self._import_document(file_path)
        
        except Exception as e:
            logger.exception(f"Error opening recent file: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open file: {str(e)}")

    def _remove_from_recent_files(self, file_path):
        """Remove a file from the recent files list."""
        try:
            recent_files = self.settings_manager.get_setting("ui", "recent_files", [])
            
            if file_path in recent_files:
                recent_files.remove(file_path)
                self.settings_manager.set_setting("ui", "recent_files", recent_files)
                
            # Update menu
            self._update_recent_files_menu()
        
        except Exception as e:
            logger.exception(f"Error removing from recent files: {e}")

    @pyqtSlot()
    def _on_clear_recent_files(self):
        """Clear the recent files list."""
        try:
            self.settings_manager.set_setting("ui", "recent_files", [])
            self._update_recent_files_menu()
        
        except Exception as e:
            logger.exception(f"Error clearing recent files: {e}")
            QMessageBox.warning(self, "Error", f"Failed to clear recent files: {str(e)}")

    def open_youtube_playlists(self, playlist_id=None):
        """Open the YouTube playlists manager.
        
        Args:
            playlist_id: Optional playlist ID to select initially
        """
        try:
            # Create a dock widget for YouTube playlists if it doesn't exist
            if not hasattr(self, 'youtube_playlists_dock'):
                from ui.youtube_playlist_view import YouTubePlaylistView
                
                # Create the view
                self.youtube_playlists_view = YouTubePlaylistView(self.db_session, self)
                
                # Create the dock widget
                self.youtube_playlists_dock = QDockWidget("YouTube Playlists", self)
                self.youtube_playlists_dock.setWidget(self.youtube_playlists_view)
                self.youtube_playlists_dock.setObjectName("youtube_playlists_dock")
                
                # Set up signals
                self.youtube_playlists_view.videoSelected.connect(self._on_playlist_video_selected)
                
                # Add to main window
                self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.youtube_playlists_dock)
            
            # Show the dock
            self.youtube_playlists_dock.show()
            self.youtube_playlists_dock.raise_()
            
            # Select specific playlist if provided
            if playlist_id is not None and hasattr(self, 'youtube_playlists_view'):
                self.youtube_playlists_view.select_playlist(playlist_id)
                
        except Exception as e:
            logger.exception(f"Error opening YouTube playlists: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open YouTube playlists: {str(e)}")
            
    def _on_playlist_video_selected(self, video_id, position):
        """Handle video selection from playlist."""
        try:
            # Create a document from the video
            from core.document_processor.handlers.youtube_handler import YouTubeHandler
            handler = YouTubeHandler()
            file_path, metadata = handler.download_from_url(f"https://www.youtube.com/watch?v={video_id}")
            
            if file_path and metadata:
                # Add document to database
                from core.knowledge_base.models import Document, init_database
                db_session = init_database()
                
                document = Document(
                    title=metadata.get('title', f'YouTube Video {video_id}'),
                    source_url=metadata.get('source_url', f'https://www.youtube.com/watch?v={video_id}'),
                    content_type='youtube',  # Changed from source_type to content_type
                    file_path=file_path,
                    metadata=metadata
                )
                
                db_session.add(document)
                db_session.commit()
                
                # Open the document
                self._open_document(document.id)
                
            else:
                QMessageBox.warning(
                    self,
                    "Error",
                    "Failed to create document from video"
                )
                
        except Exception as e:
            logger.exception(f"Failed to create document: {e}")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to create document: {str(e)}"
            )

    @pyqtSlot(bool)
    def _on_toggle_toolbar(self, checked):
        """Toggle the visibility of the toolbar.
        
        Args:
            checked (bool): Whether the toolbar should be visible
        """
        if hasattr(self, 'tool_bar'):
            self.tool_bar.setVisible(checked)
            
            # Update settings
            self.settings_manager.set_setting("ui", "toolbar_visible", checked)
            
            # Show a brief notification
            visibility = "visible" if checked else "hidden"
            self.statusBar().showMessage(f"Toolbar is now {visibility}", 3000)

    @pyqtSlot()
    def _on_new_extract(self):
        """Create a new extract from the current document."""
        try:
            # Get current document ID
            document_id = self.get_current_document_id()
            if not document_id:
                QMessageBox.warning(
                    self, "No Document Open", 
                    "Please open a document first to create an extract."
                )
                return
                
            # Get current text selection if any
            current_widget = self.content_tabs.currentWidget()
            selected_text = ""
            
            if hasattr(current_widget, '_get_selected_text'):
                selected_text = current_widget._get_selected_text()
            
            # Create a new extract
            from ui.extract_editor import ExtractEditor
            editor = ExtractEditor(
                self.db_session, 
                document_id=document_id, 
                initial_text=selected_text,
                settings_manager=self.settings_manager,
                theme_manager=self.theme_manager
            )
            editor.extractCreated.connect(self._on_extract_created)
            editor.exec()
            
        except Exception as e:
            logger.exception(f"Error creating extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to create extract: {str(e)}"
            )

    @pyqtSlot()
    def _on_sync_with_cloud(self):
        """Open the sync view to synchronize with cloud services."""
        try:
            from ui.sync_view import SyncView
            
            # Create and show the sync view
            sync_view = SyncView(self.db_session)
            
            # Add to a new tab
            tab_index = self.content_tabs.addTab(sync_view, "Cloud Sync")
            self.content_tabs.setCurrentIndex(tab_index)
            
            # Update status bar
            self.statusBar().showMessage("Cloud sync opened", 3000)
            
        except Exception as e:
            logger.exception(f"Error opening sync view: {e}")
            QMessageBox.critical(
                self, "Error",
                f"Error opening sync view: {str(e)}"
            )

