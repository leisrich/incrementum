# ui/main_window.py - Fully integrated with all components

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSplitter, QTabWidget, QToolBar, QStatusBar,
    QFileDialog, QMessageBox, QMenu, QTreeView, QListView,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QDockWidget, QInputDialog
)
from PyQt6.QtCore import Qt, QSize, QModelIndex, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtGui import QIcon, QAction, QKeySequence, QPixmap

from core.knowledge_base.models import init_database, Document, Category, Extract, LearningItem, Tag
from core.document_processor.processor import DocumentProcessor
from core.spaced_repetition.sm18 import SM18Algorithm
from core.content_extractor.nlp_extractor import NLPExtractor
from core.knowledge_base.search_engine import SearchEngine
from core.knowledge_base.tag_manager import TagManager
from core.knowledge_base.export_manager import ExportManager
from core.knowledge_network.network_builder import KnowledgeNetworkBuilder
from core.utils.settings_manager import SettingsManager

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

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """Main application window with multi-pane interface."""
    
    def __init__(self):
        super().__init__()
        
        # Initialize database session
        self.db_session = init_database()
        
        # Initialize managers and components
        self.document_processor = DocumentProcessor(self.db_session)
        self.spaced_repetition = SM18Algorithm(self.db_session)
        self.nlp_extractor = NLPExtractor(self.db_session)
        self.search_engine = SearchEngine(self.db_session)
        self.tag_manager = TagManager(self.db_session)
        self.export_manager = ExportManager(self.db_session)
        self.network_builder = KnowledgeNetworkBuilder(self.db_session)
        self.settings_manager = SettingsManager()
        
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
        
        # Initialize UI state
        self._load_recent_documents()
        self._update_status()
        
        # Set up auto-save timer
        self._setup_auto_save()
        
        # Apply settings
        self._apply_settings()
        
        # Show startup statistics if configured
        self._check_startup_statistics()
    
    def _create_actions(self):
        """Create actions for menus and toolbars."""
        # File menu actions
        self.action_import_file = QAction("Import File...", self)
        self.action_import_file.setShortcut(QKeySequence.Open)
        self.action_import_file.triggered.connect(self._on_import_file)
        
        self.action_import_url = QAction("Import from URL...", self)
        self.action_import_url.triggered.connect(self._on_import_url)
        
        self.action_import_knowledge = QAction("Import Knowledge Items...", self)
        self.action_import_knowledge.triggered.connect(self._on_import_knowledge)
        
        self.action_export_knowledge = QAction("Export Knowledge Items...", self)
        self.action_export_knowledge.triggered.connect(self._on_export_knowledge)
        
        self.action_exit = QAction("Exit", self)
        self.action_exit.setShortcut(QKeySequence.Quit)
        self.action_exit.triggered.connect(self.close)
        
        # Edit menu actions
        self.action_new_extract = QAction("New Extract...", self)
        self.action_new_extract.triggered.connect(self._on_new_extract)
        
        self.action_new_learning_item = QAction("New Learning Item...", self)
        self.action_new_learning_item.triggered.connect(self._on_new_learning_item)
        
        self.action_manage_tags = QAction("Manage Tags...", self)
        self.action_manage_tags.triggered.connect(self._on_manage_tags)
        
        # View menu actions
        self.action_toggle_category_panel = QAction("Show Category Panel", self)
        self.action_toggle_category_panel.setCheckable(True)
        self.action_toggle_category_panel.setChecked(True)
        self.action_toggle_category_panel.triggered.connect(self._on_toggle_category_panel)
        
        self.action_toggle_search_panel = QAction("Show Search Panel", self)
        self.action_toggle_search_panel.setCheckable(True)
        self.action_toggle_search_panel.setChecked(False)
        self.action_toggle_search_panel.triggered.connect(self._on_toggle_search_panel)
        
        self.action_toggle_stats_panel = QAction("Show Statistics Panel", self)
        self.action_toggle_stats_panel.setCheckable(True)
        self.action_toggle_stats_panel.setChecked(False)
        self.action_toggle_stats_panel.triggered.connect(self._on_toggle_stats_panel)
        
        # Learning menu actions
        self.action_start_review = QAction("Start Review Session", self)
        self.action_start_review.setShortcut(QKeySequence("Ctrl+R"))
        self.action_start_review.triggered.connect(self._on_start_review)
        
        self.action_browse_extracts = QAction("Browse Extracts", self)
        self.action_browse_extracts.triggered.connect(self._on_browse_extracts)
        
        self.action_browse_learning_items = QAction("Browse Learning Items", self)
        self.action_browse_learning_items.triggered.connect(self._on_browse_learning_items)
        
        # Tools menu actions
        self.action_search = QAction("Search...", self)
        self.action_search.setShortcut(QKeySequence("Ctrl+F"))
        self.action_search.triggered.connect(self._on_search)
        
        self.action_view_network = QAction("Knowledge Network", self)
        self.action_view_network.triggered.connect(self._on_view_network)
        
        self.action_backup_restore = QAction("Backup & Restore", self)
        self.action_backup_restore.triggered.connect(self._on_backup_restore)
        
        self.action_settings = QAction("Settings...", self)
        self.action_settings.triggered.connect(self._on_show_settings)
        
        self.action_statistics = QAction("Statistics Dashboard", self)
        self.action_statistics.triggered.connect(self._on_show_statistics)
    
    def _create_menu_bar(self):
        """Create the main menu bar."""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(self.action_import_file)
        file_menu.addAction(self.action_import_url)
        file_menu.addSeparator()
        
        # Recent documents submenu
        self.recent_menu = QMenu("Recent Documents", self)
        file_menu.addMenu(self.recent_menu)
        file_menu.addSeparator()
        
        # Import/Export submenu
        import_export_menu = file_menu.addMenu("Import/Export")
        import_export_menu.addAction(self.action_import_knowledge)
        import_export_menu.addAction(self.action_export_knowledge)
        
        file_menu.addSeparator()
        file_menu.addAction(self.action_exit)
        
        # Edit menu
        edit_menu = menu_bar.addMenu("&Edit")
        edit_menu.addAction(self.action_new_extract)
        edit_menu.addAction(self.action_new_learning_item)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_manage_tags)
        
        # View menu
        view_menu = menu_bar.addMenu("&View")
        view_menu.addAction(self.action_toggle_category_panel)
        view_menu.addAction(self.action_toggle_search_panel)
        view_menu.addAction(self.action_toggle_stats_panel)
        
        # Learning menu
        learning_menu = menu_bar.addMenu("&Learning")
        learning_menu.addAction(self.action_start_review)
        learning_menu.addSeparator()
        learning_menu.addAction(self.action_browse_extracts)
        learning_menu.addAction(self.action_browse_learning_items)
        
        # Tools menu
        tools_menu = menu_bar.addMenu("&Tools")
        tools_menu.addAction(self.action_search)
        tools_menu.addAction(self.action_view_network)
        tools_menu.addSeparator()
        tools_menu.addAction(self.action_backup_restore)
        tools_menu.addAction(self.action_settings)
        tools_menu.addAction(self.action_statistics)
        
        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        help_action = help_menu.addAction("Documentation")
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self._on_about)
    
    def _create_tool_bar(self):
        """Create the main toolbar."""
        self.tool_bar = QToolBar("Main Toolbar", self)
        self.tool_bar.setMovable(False)
        self.tool_bar.setIconSize(QSize(24, 24))
        
        self.tool_bar.addAction(self.action_import_file)
        self.tool_bar.addAction(self.action_import_url)
        self.tool_bar.addSeparator()
        self.tool_bar.addAction(self.action_start_review)
        self.tool_bar.addSeparator()
        self.tool_bar.addAction(self.action_search)
        self.tool_bar.addAction(self.action_statistics)
        
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
        """Create the central widget with multi-pane layout."""
        # Main widget and layout
        central_widget = QWidget(self)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create main splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left pane (categories and documents)
        self.left_pane = QWidget()
        left_layout = QVBoxLayout(self.left_pane)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
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
        self.document_list = QListView()
        self.document_model = DocumentModel(self.db_session)
        self.document_list.setModel(self.document_model)
        self.document_list.doubleClicked.connect(self._on_document_activated)
        self.document_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.document_list.customContextMenuRequested.connect(self._on_document_context_menu)
        
        # Add widgets to left layout
        left_layout.addWidget(self.category_label)
        left_layout.addWidget(self.category_tree)
        left_layout.addWidget(self.document_label)
        left_layout.addWidget(self.document_list)
        
        # Right pane (tab widget for content)
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        
        # Add initial tab for home/dashboard
        self.home_widget = QWidget()
        home_layout = QVBoxLayout(self.home_widget)
        home_layout.addWidget(QLabel("<h1>Welcome to Incrementum</h1>"))
        home_layout.addWidget(QLabel("<p>Your advanced incremental learning system.</p>"))
        
        # Add buttons for common actions
        buttons_layout = QHBoxLayout()
        
        import_button = QPushButton("Import Document")
        import_button.clicked.connect(self._on_import_file)
        buttons_layout.addWidget(import_button)
        
        review_button = QPushButton("Start Review Session")
        review_button.clicked.connect(self._on_start_review)
        buttons_layout.addWidget(review_button)
        
        search_button = QPushButton("Search")
        search_button.clicked.connect(self._on_search)
        buttons_layout.addWidget(search_button)
        
        stats_button = QPushButton("Statistics Dashboard")
        stats_button.clicked.connect(self._on_show_statistics)
        buttons_layout.addWidget(stats_button)
        
        home_layout.addLayout(buttons_layout)
        
        # Stats overview section
        stats_overview = QWidget()
        stats_layout = QVBoxLayout(stats_overview)
        stats_layout.addWidget(QLabel("<h2>Learning Overview</h2>"))
        
        # Get some basic stats
        doc_count = self.db_session.query(func.count(Document.id)).scalar() or 0
        extract_count = self.db_session.query(func.count(Extract.id)).scalar() or 0
        item_count = self.db_session.query(func.count(LearningItem.id)).scalar() or 0
        
        # Due items
        due_count = self.db_session.query(LearningItem).filter(
            (LearningItem.next_review <= datetime.utcnow()) | 
            (LearningItem.next_review == None)
        ).count()
        
        stats_layout.addWidget(QLabel(f"<p>Documents: <b>{doc_count}</b></p>"))
        stats_layout.addWidget(QLabel(f"<p>Extracts: <b>{extract_count}</b></p>"))
        stats_layout.addWidget(QLabel(f"<p>Learning Items: <b>{item_count}</b></p>"))
        stats_layout.addWidget(QLabel(f"<p>Items Due for Review: <b>{due_count}</b></p>"))
        
        home_layout.addWidget(stats_overview)
        home_layout.addStretch()
        
        self.tab_widget.addTab(self.home_widget, "Home")
        
        # Add panes to splitter
        self.main_splitter.addWidget(self.left_pane)
        self.main_splitter.addWidget(self.tab_widget)
        
        # Set split ratio based on settings
        default_ratio = self.settings_manager.get_setting("ui", "default_split_ratio", 0.25)
        total_width = self.width()
        left_width = int(total_width * default_ratio)
        right_width = total_width - left_width
        self.main_splitter.setSizes([left_width, right_width])
        
        # Add splitter to main layout
        main_layout.addWidget(self.main_splitter)
        
        # Set central widget
        self.setCentralWidget(central_widget)
    
    def _create_docks(self):
        """Create dock widgets."""
        # Search dock
        self.search_dock = QDockWidget("Search", self)
        self.search_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.search_view = SearchView(self.db_session)
        self.search_view.itemSelected.connect(self._on_search_item_selected)
        self.search_dock.setWidget(self.search_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.search_dock)
        self.search_dock.hide()  # Initially hidden
        
        # Statistics dock
        self.stats_dock = QDockWidget("Statistics", self)
        self.stats_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        self.stats_view = StatisticsWidget(self.db_session)
        self.stats_dock.setWidget(self.stats_view)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.stats_dock)
        self.stats_dock.hide()  # Initially hidden
    
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
        """Set up auto-save timer."""
        # Get auto-save interval from settings
        interval_minutes = self.settings_manager.get_setting("general", "auto_save_interval", 5)
        interval_ms = interval_minutes * 60 * 1000
        
        # Create timer
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self._on_auto_save)
        self.auto_save_timer.start(interval_ms)
    
    def _apply_settings(self):
        """Apply settings to UI."""
        # Left panel visibility
        show_category_panel = self.settings_manager.get_setting("ui", "show_category_panel", True)
        self.left_pane.setVisible(show_category_panel)
        self.action_toggle_category_panel.setChecked(show_category_panel)
    
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
        """Handler for importing from URL."""
        # In a real app, we'd show a dialog to enter URL
        # For now, just use a simple QInputDialog
        
        url, ok = QInputDialog.getText(
            self, "Import from URL", "Enter URL:"
        )
        
        if ok and url:
            self.status_label.setText(f"Importing from URL: {url}...")
            
            # This would be done in a background thread in a real app
            document = self.document_processor.import_from_url(url)
            
            if document:
                self.status_label.setText(f"Imported: {document.title}")
                self._load_recent_documents()
                self._update_status()
                
                # Open the document
                self._open_document(document.id)
            else:
                QMessageBox.warning(
                    self, "Import Failed", 
                    f"Failed to import from URL: {url}"
                )
                self.status_label.setText("Import failed")
    
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
        
        current_widget = self.tab_widget.currentWidget()
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
    
    def _open_document(self, document_id):
        """Open a document in a new tab."""
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return
        
        # Update last accessed time
        document.last_accessed = datetime.utcnow()
        self.db_session.commit()
        
        # Create appropriate document view based on content type
        if document.content_type == 'pdf':
            document_view = PDFViewWidget(document, self.db_session)
            document_view.extractCreated.connect(self._on_extract_created)
        else:
            document_view = DocumentView(document, self.db_session)
        
        # Add to tab widget
        tab_index = self.tab_widget.addTab(document_view, document.title)
        self.tab_widget.setCurrentIndex(tab_index)
    
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
            
        tab_index = self.tab_widget.addTab(extract_view, tab_title)
        self.tab_widget.setCurrentIndex(tab_index)
    
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
        tab_index = self.tab_widget.addTab(item_editor, f"Item {item_id}")
        self.tab_widget.setCurrentIndex(tab_index)
    
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
            tab_index = self.tab_widget.addTab(item_editor, "New Learning Item")
            self.tab_widget.setCurrentIndex(tab_index)
    
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
        self.left_pane.setVisible(checked)
        
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
        menu.addSeparator()
        
        edit_tags_action = menu.addAction("Edit Tags")
        change_category_action = menu.addAction("Change Category")
        menu.addSeparator()
        
        delete_action = menu.addAction("Delete")
        
        # Connect actions
        open_action.triggered.connect(lambda: self._open_document(document_id))
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
    
    @pyqtSlot(int)
    def _on_tab_close_requested(self, index):
        """Handler for tab close request."""
        if index > 0:  # Don't close the home tab
            widget = self.tab_widget.widget(index)
            self.tab_widget.removeTab(index)
            widget.deleteLater()
    
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
        tab_index = self.tab_widget.addTab(review_view, "Review Session")
        self.tab_widget.setCurrentIndex(tab_index)
    
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
        tab_index = self.tab_widget.addTab(network_view, "Knowledge Network")
        self.tab_widget.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_backup_restore(self):
        """Handler for backup and restore."""
        # Create backup view
        backup_view = BackupView(self.db_session)
        
        # Add to tab widget
        tab_index = self.tab_widget.addTab(backup_view, "Backup & Restore")
        self.tab_widget.setCurrentIndex(tab_index)
    
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
    
    @pyqtSlot()
    def _on_show_statistics(self):
        """Handler for showing statistics dashboard."""
        self.stats_dock.show()
        self.action_toggle_stats_panel.setChecked(True)
        
        # Create statistics view in tab
        stats_view = StatisticsWidget(self.db_session)
        
        # Add to tab widget
        tab_index = self.tab_widget.addTab(stats_view, "Statistics")
        self.tab_widget.setCurrentIndex(tab_index)
    
    @pyqtSlot()
    def _on_recent_document_selected(self):
        """Handler for selecting a document from the recent menu."""
        action = self.sender()
        if action:
            document_id = action.data()
            self._open_document(document_id)
    
    @pyqtSlot(Extract)
    def _on_extract_created(self, extract):
        """Handler for extract creation from PDF view."""
        # Open extract view
        self._open_extract(extract.id)
        
        # Auto suggest tags if enabled
        auto_suggest = self.settings_manager.get_setting("document", "auto_suggest_tags", True)
        if auto_suggest:
            suggested_tags = self.tag_manager.suggest_tags_for_extract(extract.id)
            
            if suggested_tags:
                # Add tags automatically
                for tag in suggested_tags:
                    self.tag_manager.add_extract_tag(extract.id, tag)
    
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
        current_index = self.tab_widget.currentIndex()
        self.tab_widget.removeTab(current_index)
    
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
        </ul>
        """
        
        QMessageBox.about(self, "About Incrementum", about_text)
    
    @pyqtSlot()
    def _on_auto_save(self):
        """Auto-save handler triggered by timer."""
        # Save any unsaved changes
        # This is a placeholder - in a real app, we'd check for unsaved changes
        # and save them
        
        # Update status
        self.status_label.setText(f"Auto-saved at {datetime.now().strftime('%H:%M:%S')}")
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Check for unsaved changes
        # This is a placeholder - in a real app, we'd check for unsaved changes
        # and prompt the user to save them
        
        # Accept the event to close the window
        event.accept()
