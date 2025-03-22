# ui/main_window.py - Fully integrated with all components

import os
import sys
import logging
import json
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
    QInputDialog
)
from PyQt6.QtCore import Qt, QSize, QModelIndex, pyqtSignal, pyqtSlot, QTimer, QPoint, QThread, QByteArray
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap, QAction

from core.knowledge_base.models import init_database, Document, Category, Extract, LearningItem, Tag
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
from core.utils.shortcuts import ShortcutManager
from .arxiv_dialog import ArxivDialog
from core.document_processor.summarizer import SummarizeDialog
from .queue_view import QueueView
from ui.dialogs.url_import_dialog import URLImportDialog
from ui.dialogs.content_processor_dialog import ContentProcessorDialog
from ui.dialogs.rss_feed_dialog import RSSFeedDialog

logger = logging.getLogger(__name__)

class DockablePDFView(QDockWidget):
    """Dockable widget containing a PDF viewer."""
    
    extractCreated = pyqtSignal(int)
    
    def __init__(self, document, db_session, parent=None):
        title = f"PDF: {document.title}"
        super().__init__(title, parent)
        
        # Set object name for state saving
        self.setObjectName(f"PDFDock_{document.id}")
        
        self.document = document
        self.db_session = db_session
        
        # Create PDF viewer widget
        self.pdf_widget = PDFViewWidget(document, db_session)
        self.pdf_widget.extractCreated.connect(self.extractCreated.emit)
        
        # Set as dock widget content
        self.setWidget(self.pdf_widget)
        
        # Allow positioning in all areas
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        
        # Allow closable, floatable, and movable
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        
        # Set initial size
        self.setMinimumSize(600, 800)
    
    def closeEvent(self, event):
        """Handle close event to save the PDF position."""
        if hasattr(self.pdf_widget, '_save_position'):
            self.pdf_widget._save_position()
        super().closeEvent(event)

class MainWindow(QMainWindow):
    """Main application window with multi-pane interface."""
    
    # Define signals
    document_changed = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        
        # Flag to track initialization status
        self._initialization_complete = False
        
        # Initialize database session
        self.db_session = init_database()
        
        # Initialize managers and components
        self.document_processor = DocumentProcessor(self.db_session)
        self.spaced_repetition = FSRSAlgorithm(self.db_session)
        self.nlp_extractor = NLPExtractor(self.db_session)
        self.search_engine = SearchEngine(self.db_session)
        self.tag_manager = TagManager(self.db_session)
        self.export_manager = ExportManager(self.db_session)
        self.network_builder = KnowledgeNetworkBuilder(self.db_session)
        self.settings_manager = SettingsManager()
        self.theme_manager = ThemeManager(self.settings_manager)
        self.queue_manager = FSRSAlgorithm(self.db_session)
        self.rss_manager = RSSFeedManager(self.db_session, self.settings_manager)
        
        # Set window properties
        self.setWindowTitle("Incrementum - Incremental Learning System")
        self.setMinimumSize(1200, 800)
        
        # Create UI components
        self._create_actions()
        self._create_menu_bar()
        self._create_tool_bar()
        self._create_status_bar()
        self._create_central_widget()
        self._create_docks()
        self._setup_dock_options()
        
        # Initialize UI state
        self._load_recent_documents()
        self._update_status()
        
        # Restore saved layout if available
        self._restore_saved_layout()
        
        # Restore session (open tabs) if available
        self._restore_session()
        
        # Set up auto-save timer
        self._setup_auto_save()
        
        # Apply settings
        self._apply_settings()
        
        # Show startup statistics if configured
        self._check_startup_statistics()
        
        # Start RSS feed updater if enabled
        self._start_rss_updater()
        
        # Initialization is complete
        self._initialization_complete = True
        
        # Add a timer to save session after the window is shown
        QTimer.singleShot(1000, self._check_session_state)
        
        # Connect exit action
        self.action_exit.triggered.connect(self.close)
    
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
        """Create actions for menus and toolbars with keyboard shortcuts."""
        # File menu actions
        self.action_import_file = QAction("Import File...", self)
        self.action_import_file.setShortcut(ShortcutManager.IMPORT_FILE)
        self.action_import_file.triggered.connect(self._on_import_file)
        
        self.action_import_url = QAction("Import from URL...", self)
        self.action_import_url.setShortcut(ShortcutManager.IMPORT_URL)
        self.action_import_url.triggered.connect(self._on_import_url)
        
        self.action_import_knowledge = QAction("Import Knowledge Items...", self)
        self.action_import_knowledge.triggered.connect(self._on_import_knowledge)
        
        self.action_export_knowledge = QAction("Export Knowledge Items...", self)
        self.action_export_knowledge.triggered.connect(self._on_export_knowledge)
        
        self.action_save = QAction("Save", self)
        self.action_save.setShortcut(ShortcutManager.SAVE)
        self.action_save.triggered.connect(self._on_save)
        
        self.action_exit = QAction("Exit", self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_exit.triggered.connect(self.close)
        
        # Edit menu actions
        self.action_new_extract = QAction("New Extract...", self)
        self.action_new_extract.setShortcut(ShortcutManager.CREATE_EXTRACT)
        self.action_new_extract.triggered.connect(self._on_new_extract)
        
        self.action_new_learning_item = QAction("New Learning Item...", self)
        self.action_new_learning_item.setShortcut(ShortcutManager.NEW_LEARNING_ITEM)
        self.action_new_learning_item.triggered.connect(self._on_new_learning_item)
        
        self.action_add_bookmark = QAction("Add Bookmark", self)
        self.action_add_bookmark.setShortcut(ShortcutManager.ADD_BOOKMARK)
        self.action_add_bookmark.triggered.connect(self._on_add_bookmark)
        
        self.action_highlight = QAction("Highlight Selection", self)
        self.action_highlight.setShortcut(ShortcutManager.HIGHLIGHT)
        self.action_highlight.triggered.connect(self._on_highlight_selection)
        
        self.action_manage_tags = QAction("Manage Tags...", self)
        self.action_manage_tags.triggered.connect(self._on_manage_tags)
        
        # View menu actions
        self.action_toggle_category_panel = QAction("Show Category Panel", self)
        self.action_toggle_category_panel.setCheckable(True)
        self.action_toggle_category_panel.setChecked(True)
        self.action_toggle_category_panel.setShortcut(ShortcutManager.TOGGLE_CATEGORY_PANEL)
        self.action_toggle_category_panel.triggered.connect(self._on_toggle_category_panel)
        
        self.action_toggle_search_panel = QAction("Show Search Panel", self)
        self.action_toggle_search_panel.setCheckable(True)
        self.action_toggle_search_panel.setChecked(False)
        self.action_toggle_search_panel.setShortcut(ShortcutManager.TOGGLE_SEARCH_PANEL)
        self.action_toggle_search_panel.triggered.connect(self._on_toggle_search_panel)
        
        self.action_toggle_stats_panel = QAction("Show Statistics Panel", self)
        self.action_toggle_stats_panel.setCheckable(True)
        self.action_toggle_stats_panel.setChecked(False)
        self.action_toggle_stats_panel.setShortcut(ShortcutManager.TOGGLE_STATS_PANEL)
        self.action_toggle_stats_panel.triggered.connect(self._on_toggle_stats_panel)
        
        self.action_toggle_queue_panel = QAction("Show Queue Panel", self)
        self.action_toggle_queue_panel.setCheckable(True)
        self.action_toggle_queue_panel.setChecked(False)
        self.action_toggle_queue_panel.triggered.connect(self._on_toggle_queue_panel)
        self.action_toggle_queue_panel.setShortcut(ShortcutManager.TOGGLE_QUEUE_PANEL)
        
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
        """Create the menu bar with all menus."""
        self.menu_bar = self.menuBar()
        
        # File menu
        self.file_menu = self.menu_bar.addMenu("&File")
        
        # Add new extract action
        self.action_new_extract = QAction("New &Extract...", self)
        self.action_new_extract.setShortcut(QKeySequence("Ctrl+E"))
        self.action_new_extract.triggered.connect(self._on_new_extract)
        self.file_menu.addAction(self.action_new_extract)
        
        # Add new learning item action
        self.action_new_item = QAction("New Learning &Item...", self)
        self.action_new_item.setShortcut(QKeySequence("Ctrl+I"))
        self.action_new_item.triggered.connect(self._on_new_learning_item)
        self.file_menu.addAction(self.action_new_item)
        
        self.file_menu.addSeparator()
        
        # Add save action
        self.action_save = QAction("&Save", self)
        self.action_save.setShortcut(QKeySequence.StandardKey.Save)
        self.action_save.triggered.connect(self._on_save)
        self.file_menu.addAction(self.action_save)
        
        self.file_menu.addSeparator()
        
        # Import menu - add as a separate top-level menu
        self.import_menu = self.menu_bar.addMenu("&Import")
        
        # Add import from file action
        self.action_import_file = QAction("Import from &File...", self)
        self.action_import_file.setStatusTip("Import a document from a file")
        self.action_import_file.triggered.connect(self._on_import_file)
        self.import_menu.addAction(self.action_import_file)
        
        # Add import from URL action
        self.action_import_url = QAction("Import from &URL...", self)
        self.action_import_url.setStatusTip("Import a document from a URL")
        self.action_import_url.triggered.connect(self._on_import_url)
        self.import_menu.addAction(self.action_import_url)
        
        # Add web browser action if enabled in settings
        if self.settings_manager.get_setting("ui", "web_browser_enabled", True):
            self.action_web_browser = QAction("Open &Web Browser...", self)
            self.action_web_browser.setStatusTip("Browse the web and create extracts")
            self.action_web_browser.setShortcut(QKeySequence("Ctrl+B"))
            self.action_web_browser.triggered.connect(self._on_open_web_browser)
            self.import_menu.addAction(self.action_web_browser)
        
        # Add import knowledge action
        self.action_import_knowledge = QAction("Import &Knowledge Base...", self)
        self.action_import_knowledge.setStatusTip("Import knowledge from a backup file")
        self.action_import_knowledge.triggered.connect(self._on_import_knowledge)
        self.import_menu.addAction(self.action_import_knowledge)
        
        # Export menu - remains in File menu
        self.file_menu.addSeparator()
        
        # Add export knowledge action
        self.action_export_knowledge = QAction("&Export Knowledge Base...", self)
        self.action_export_knowledge.triggered.connect(self._on_export_knowledge)
        self.file_menu.addAction(self.action_export_knowledge)
        
        self.file_menu.addSeparator()
        
        # Recent documents submenu
        self.recent_menu = QMenu("Recent Documents", self)
        self.file_menu.addMenu(self.recent_menu)
        
        self.file_menu.addSeparator()
        
        # Add exit action
        self.action_exit = QAction("E&xit", self)
        self.action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.file_menu.addAction(self.action_exit)
        
        # Edit menu
        edit_menu = self.menu_bar.addMenu("&Edit")
        edit_menu.addAction(self.action_new_extract)
        edit_menu.addAction(self.action_new_learning_item)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_manage_tags)
        
        # View menu
        self.view_menu = self.menu_bar.addMenu("&View")
        
        # Panel toggles
        panels_menu = self.view_menu.addMenu("Panels")
        panels_menu.addAction(self.action_toggle_category_panel)
        panels_menu.addAction(self.action_toggle_search_panel)
        panels_menu.addAction(self.action_toggle_stats_panel)
        panels_menu.addAction(self.action_toggle_queue_panel)  # Add queue panel toggle
        
        # Add dock arrangement actions
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.action_tile_docks)
        self.view_menu.addAction(self.action_cascade_docks)
        self.view_menu.addAction(self.action_tab_docks)
        
        # Learning menu
        learning_menu = self.menu_bar.addMenu("&Learning")
        learning_menu.addAction(self.action_start_review)
        learning_menu.addSeparator()
        learning_menu.addAction(self.action_browse_extracts)
        learning_menu.addAction(self.action_browse_learning_items)
        
        # Tools menu
        self.tools_menu = self.menu_bar.addMenu("&Tools")
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
        
        # NOW ADD THE RSS FEEDS ACTION TO THE TOOLS MENU
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.action_rss_feeds)
        
        # NOW ADD THE ADDITIONAL TOOL ACTIONS THAT WERE ORIGINALLY IN _create_actions
        self.tools_menu.addAction(self.action_tag_manager)
        self.tools_menu.addAction(self.action_batch_processor)
        self.tools_menu.addAction(self.action_review_manager)
        self.tools_menu.addAction(self.action_backup)
        
        # Help menu
        help_menu = self.menu_bar.addMenu("&Help")
        help_action = help_menu.addAction("Documentation")
        layout_help_action = help_menu.addAction("Interface Layout")
        layout_help_action.triggered.connect(self._on_layout_help)
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._on_about)
    
    def _create_tool_bar(self):
        """Create the toolbar with main actions."""
        self.tool_bar = QToolBar()
        self.tool_bar.setObjectName("MainToolBar")
        self.tool_bar.setIconSize(QSize(24, 24))
        self.tool_bar.setMovable(False)
        
        # Add common actions
        self.tool_bar.addAction(self.action_import_file)
        self.tool_bar.addAction(self.action_import_url)
        
        # Add web browser action if enabled
        if self.settings_manager.get_setting("ui", "web_browser_enabled", True):
            self.tool_bar.addAction(self.action_web_browser)
        
        self.tool_bar.addAction(self.action_save)
        self.tool_bar.addSeparator()
        
        self.tool_bar.addAction(self.action_add_bookmark)
        self.tool_bar.addAction(self.action_highlight)
        self.tool_bar.addSeparator()
        self.tool_bar.addAction(self.action_generate_items)
        self.tool_bar.addSeparator()
        self.tool_bar.addAction(self.action_start_review)
        self.tool_bar.addAction(self.action_view_queue)
        self.tool_bar.addAction(self.action_prev_document)
        self.tool_bar.addAction(self.action_read_next)
        self.tool_bar.addSeparator()
        self.tool_bar.addAction(self.action_search)
        
        self.addToolBar(self.tool_bar)
    
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
        """Create dock widgets."""
        # Categories dock
        self.category_dock = QDockWidget("Categories", self)
        self.category_dock.setObjectName("CategoriesDock")
        self.category_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.category_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        
        # Create category widget
        category_widget = QWidget()
        category_layout = QVBoxLayout(category_widget)
        
        # Category tree
        self.category_label = QLabel("Categories")
        self.category_tree = QTreeView()
        self.category_model = CategoryModel(self.db_session)
        self.category_tree.setModel(self.category_model)
        self.category_tree.clicked.connect(self._on_category_selected)
        self.category_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.category_tree.customContextMenuRequested.connect(self._on_category_context_menu)
        
        # Document list
        self.document_label = QLabel("Documents")
        self.documents_list = QListView()
        self.document_model = DocumentModel(self.db_session)
        self.documents_list.setModel(self.document_model)
        self.documents_list.doubleClicked.connect(self._on_document_activated)
        self.documents_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.documents_list.customContextMenuRequested.connect(self._on_document_context_menu)
        
        # Add widgets to category layout
        category_layout.addWidget(self.category_label)
        category_layout.addWidget(self.category_tree)
        category_layout.addWidget(self.document_label)
        category_layout.addWidget(self.documents_list)
        
        # Set the dock widget's content
        self.category_dock.setWidget(category_widget)
        
        # Add dock to main window
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.category_dock)
        
        # Get visibility setting
        show_category_panel = self.settings_manager.get_setting("ui", "show_category_panel", True)
        if not show_category_panel:
            self.category_dock.hide()
        
        # Search dock
        self.search_dock = QDockWidget("Search", self)
        self.search_dock.setObjectName("SearchDock")
        self.search_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.search_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.search_view = SearchView(self.db_session)
        self.search_view.itemSelected.connect(self._on_search_item_selected)
        self.search_dock.setWidget(self.search_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.search_dock)
        self.search_dock.hide()  # Initially hidden
        
        # Statistics dock
        self.stats_dock = QDockWidget("Statistics", self)
        self.stats_dock.setObjectName("StatisticsDock")
        self.stats_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.stats_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.stats_view = StatisticsWidget(self.db_session)
        self.stats_dock.setWidget(self.stats_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.stats_dock)
        self.stats_dock.hide()  # Initially hidden
        
        # Queue dock
        self.queue_dock = QDockWidget("Reading Queue", self)
        self.queue_dock.setObjectName("QueueDock")
        self.queue_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.queue_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        
        # Create queue widget
        self.queue_view = QueueView(self.db_session, self.settings_manager)
        self.queue_view.documentSelected.connect(self._open_document)
        # Connect document changed signal to update queue view
        self.document_changed.connect(self.queue_view.set_current_document)
        
        # Set as dock widget content
        self.queue_dock.setWidget(self.queue_view)
        
        # Initially hidden
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.queue_dock)
        self.queue_dock.setVisible(False)

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
        self.recent_menu.clear()
        
        # Get max recent documents from settings
        max_recent = self.settings_manager.get_setting("general", "max_recent_documents", 10)
        
        # Get recent documents from database
        recent_docs = self.db_session.query(Document).order_by(
            Document.last_accessed.desc()
        ).limit(max_recent).all()
        
        for doc in recent_docs:
            action = self.recent_menu.addAction(doc.title)
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
            
        # Get the widget and check if it's a document
        widget = self.content_tabs.widget(current_tab_idx)
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
            self.theme_manager.apply_theme(app)
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
        
        # Add to tab widget
        tab_index = self.content_tabs.addTab(document_view, document.title)
        self.content_tabs.setCurrentIndex(tab_index)
    
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
    
    def _open_learning_item(self, item_id):
        """Open a learning item in a new tab."""
        item = self.db_session.query(LearningItem).get(item_id)
        if not item:
            logger.error(f"Learning item not found: {item_id}")
            return
        
        # Create learning item editor
        item_editor = LearningItemEditor(self.db_session, item_id)
        item_editor.itemSaved.connect(self._on_learning_item_saved)
        item_editor.itemDeleted.connect(self._on_learning_item_deleted)
        
        # Add to tab widget
        tab_index = self.content_tabs.addTab(item_editor, f"Item {item_id}")
        self.content_tabs.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_new_extract(self):
        """Handler for creating a new extract."""
        # Get document to associate with
        documents = self.db_session.query(Document).order_by(Document.title).all()
        document_titles = [doc.title for doc in documents]
        
        document_title, ok = QInputDialog.getItem(
            self, "Select Document", 
            "Select document to associate with extract:",
            document_titles, 0, False
        )
        
        if ok and document_title:
            # Find document
            document = next((doc for doc in documents if doc.title == document_title), None)
            if document:
                # Create new extract
                extract = Extract(
                    content="",
                    document_id=document.id,
                    priority=50,
                    created_date=datetime.utcnow(),
                    processed=False
                )
                
                self.db_session.add(extract)
                self.db_session.commit()
                
                # Open extract
                self._open_extract(extract.id)
    
    @pyqtSlot()
    def _on_new_learning_item(self):
        """Handler for creating a new learning item."""
        # Get extract to associate with
        extracts = self.db_session.query(Extract).order_by(Extract.created_date.desc()).limit(20).all()
        
        if not extracts:
            QMessageBox.warning(
                self, "No Extracts", 
                "No extracts available to create learning item from."
            )
            return
        
        # Create display list
        extract_displays = []
        for extract in extracts:
            content = extract.content
            if len(content) > 50:
                content = content[:47] + "..."
            
            document_title = extract.document.title if extract.document else "No document"
            display = f"{content} ({document_title})"
            extract_displays.append(display)
        
        extract_display, ok = QInputDialog.getItem(
            self, "Select Extract", 
            "Select extract to create learning item from:",
            extract_displays, 0, False
        )
        
        if ok and extract_display:
            # Find extract
            index = extract_displays.index(extract_display)
            extract = extracts[index]
            
            # Create learning item editor
            item_editor = LearningItemEditor(self.db_session, extract_id=extract.id)
            item_editor.itemSaved.connect(self._on_learning_item_saved)
            
            # Add to tab widget
            tab_index = self.content_tabs.addTab(item_editor, "New Learning Item")
            self.content_tabs.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_manage_tags(self):
        """Handler for managing tags."""
        QMessageBox.information(
            self, "Manage Tags", 
            "Tag management interface would be shown here."
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
        """Handler for toggling queue panel visibility."""
        if checked:
            self.queue_dock.show()
        else:
            self.queue_dock.hide()
    
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
            # Create category
            category = Category(
                name=name,
                parent_id=parent_id
            )
            
            self.db_session.add(category)
            self.db_session.commit()
            
            # Reload category model
            self.category_model._reload_categories()
    
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
            # Update category
            category.name = name
            self.db_session.commit()
            
            # Reload category model
            self.category_model._reload_categories()
    
    @pyqtSlot(int)
    def _on_delete_category(self, category_id):
        """Handler for deleting a category."""
        category = self.db_session.query(Category).get(category_id)
        if not category:
            return
        
        # Check if category has children
        children_count = self.db_session.query(Category).filter(Category.parent_id == category_id).count()
        
        if children_count > 0:
            QMessageBox.warning(
                self, "Cannot Delete", 
                "Cannot delete category with subcategories."
            )
            return
        
        # Check if category has documents
        documents_count = self.db_session.query(Document).filter(Document.category_id == category_id).count()
        
        # Confirmation
        msg = f"Are you sure you want to delete category '{category.name}'?"
        
        if documents_count > 0:
            msg += f"\n\nThis will remove the category from {documents_count} documents."
        
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Update documents to remove category
            self.db_session.query(Document).filter(
                Document.category_id == category_id
            ).update({Document.category_id: None})
            
            # Delete category
            self.db_session.delete(category)
            self.db_session.commit()
            
            # Reload category model
            self.category_model._reload_categories()
    
    @pyqtSlot(QModelIndex)
    def _on_document_activated(self, index):
        """Handler for document activation (double-click)."""
        document_id = self.document_model.get_document_id(index)
        if document_id is not None:
            self._open_document(document_id)
    
    @pyqtSlot(QPoint)
    def _on_document_context_menu(self, pos):
        """Show context menu for document list."""
        index = self.documents_list.indexAt(pos)
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
        
        menu.exec(self.documents_list.viewport().mapToGlobal(pos))
    
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
    
    @pyqtSlot()
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
