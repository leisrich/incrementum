import logging
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QTextEdit, QComboBox, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QAction

from core.knowledge_base.models import RSSFeed, RSSFeedEntry, Document
from core.utils.rss_feed_manager import RSSFeedManager
from ui.dialogs.rss_feed_dialog import RSSFeedDialog

logger = logging.getLogger(__name__)

class RSSView(QWidget):
    """View for managing and reading RSS feeds."""
    
    open_document_signal = pyqtSignal(int)  # Document ID
    
    def __init__(self, db_session):
        super().__init__()
        self.db_session = db_session
        self.rss_manager = RSSFeedManager(db_session)
        
        self.current_feed_id = None
        
        self.initUI()
        self.load_feeds()
    
    def initUI(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh Feeds")
        self.refresh_btn.clicked.connect(self.refresh_feeds)
        toolbar_layout.addWidget(self.refresh_btn)
        
        self.add_feed_btn = QPushButton("Add Feed")
        self.add_feed_btn.clicked.connect(self._on_add_feed)
        toolbar_layout.addWidget(self.add_feed_btn)
        
        self.manage_feeds_btn = QPushButton("Manage Feeds")
        self.manage_feeds_btn.clicked.connect(self._on_manage_feeds)
        toolbar_layout.addWidget(self.manage_feeds_btn)
        
        toolbar_layout.addStretch()
        
        layout.addLayout(toolbar_layout)
        
        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Feed list
        feed_widget = QWidget()
        feed_layout = QVBoxLayout(feed_widget)
        feed_layout.setContentsMargins(0, 0, 0, 0)
        
        feed_label = QLabel("Feeds")
        feed_layout.addWidget(feed_label)
        
        self.feed_table = QTableWidget()
        self.feed_table.setColumnCount(2)
        self.feed_table.setHorizontalHeaderLabels(["Title", "Unread"])
        self.feed_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.feed_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.feed_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.feed_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.feed_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.feed_table.customContextMenuRequested.connect(self._on_feed_context_menu)
        self.feed_table.itemSelectionChanged.connect(self._on_feed_selection_changed)
        
        feed_layout.addWidget(self.feed_table)
        
        # Entries list and content splitter
        entries_content_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Entries widget
        entries_widget = QWidget()
        entries_layout = QVBoxLayout(entries_widget)
        entries_layout.setContentsMargins(0, 0, 0, 0)
        
        entries_header = QHBoxLayout()
        self.entries_label = QLabel("Entries")
        entries_header.addWidget(self.entries_label)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All Entries", "Unread Only", "Imported Only"])
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        entries_header.addWidget(self.filter_combo)
        
        entries_layout.addLayout(entries_header)
        
        self.entries_table = QTableWidget()
        self.entries_table.setColumnCount(3)
        self.entries_table.setHorizontalHeaderLabels(["Title", "Date", "Status"])
        self.entries_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.entries_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.entries_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.entries_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.entries_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.entries_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.entries_table.customContextMenuRequested.connect(self._on_entry_context_menu)
        self.entries_table.itemSelectionChanged.connect(self._on_entry_selection_changed)
        
        entries_layout.addWidget(self.entries_table)
        
        # Content preview
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        content_header = QHBoxLayout()
        content_header.addWidget(QLabel("Preview"))
        
        self.import_btn = QPushButton("Import")
        self.import_btn.clicked.connect(self._on_import_current)
        self.import_btn.setEnabled(False)
        content_header.addWidget(self.import_btn)
        
        self.view_btn = QPushButton("View")
        self.view_btn.clicked.connect(self._on_view_current)
        self.view_btn.setEnabled(False)
        content_header.addWidget(self.view_btn)
        
        content_layout.addLayout(content_header)
        
        self.content_preview = QTextEdit()
        self.content_preview.setReadOnly(True)
        content_layout.addWidget(self.content_preview)
        
        # Add widgets to splitters
        entries_content_splitter.addWidget(entries_widget)
        entries_content_splitter.addWidget(content_widget)
        entries_content_splitter.setSizes([200, 400])
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(entries_content_splitter)
        
        splitter.addWidget(feed_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([200, 600])
        
        layout.addWidget(splitter)
    
    def load_feeds(self):
        """Load RSS feeds into the table."""
        try:
            # Get all feeds
            feeds = self.db_session.query(RSSFeed).order_by(RSSFeed.title).all()
            
            # Set table rows
            self.feed_table.setRowCount(len(feeds))
            
            for row, feed in enumerate(feeds):
                # Title
                title_item = QTableWidgetItem(feed.title)
                title_item.setData(Qt.ItemDataRole.UserRole, feed.id)
                self.feed_table.setItem(row, 0, title_item)
                
                # Get unread count
                unread_count = self.rss_manager.get_unread_count(feed.id)
                
                # Unread
                unread_item = QTableWidgetItem(str(unread_count))
                self.feed_table.setItem(row, 1, unread_item)
            
            # Clear entries
            self.entries_table.setRowCount(0)
            self.content_preview.clear()
            
        except Exception as e:
            logger.exception(f"Error loading RSS feeds: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while loading RSS feeds: {str(e)}"
            )
    
    def load_feed_entries(self, feed_id: int):
        """Load entries for the selected feed."""
        try:
            self.current_feed_id = feed_id
            
            # Get feed
            feed = self.db_session.query(RSSFeed).get(feed_id)
            if not feed:
                logger.error(f"Feed not found: {feed_id}")
                return
                
            # Update label
            self.entries_label.setText(f"Entries - {feed.title}")
            
            # Get filter type
            filter_idx = self.filter_combo.currentIndex()
            
            # Get entries based on filter
            if filter_idx == 1:  # Unread Only
                entries = self.rss_manager.get_unread_entries(feed_id)
            elif filter_idx == 2:  # Imported Only
                entries = self.rss_manager.get_imported_entries(feed_id)
            else:  # All Entries
                entries = self.rss_manager.get_all_entries(feed_id)
            
            # Set table rows
            self.entries_table.setRowCount(len(entries))
            
            for row, entry in enumerate(entries):
                # Title
                title_item = QTableWidgetItem(entry.title)
                title_item.setData(Qt.ItemDataRole.UserRole, entry.id)
                self.entries_table.setItem(row, 0, title_item)
                
                # Date
                date_str = entry.publish_date.strftime("%Y-%m-%d") if entry.publish_date else ""
                date_item = QTableWidgetItem(date_str)
                self.entries_table.setItem(row, 1, date_item)
                
                # Status
                status = "Imported" if entry.document_id else "New"
                status_item = QTableWidgetItem(status)
                self.entries_table.setItem(row, 2, status_item)
            
            # Clear content preview
            self.content_preview.clear()
            
        except Exception as e:
            logger.exception(f"Error loading feed entries: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while loading feed entries: {str(e)}"
            )
    
    def refresh_feeds(self):
        """Refresh all feeds."""
        try:
            # Show progress message
            QMessageBox.information(
                self, "Refreshing Feeds", 
                "Refreshing all feeds. This may take a moment..."
            )
            
            # Refresh feeds
            updated = self.rss_manager.update_all_feeds()
            
            # Reload feeds
            self.load_feeds()
            
            # If a feed was selected, reload its entries
            if self.current_feed_id:
                self.load_feed_entries(self.current_feed_id)
            
            # Show success message
            QMessageBox.information(
                self, "Feeds Updated", 
                f"Successfully updated {updated} feeds."
            )
            
        except Exception as e:
            logger.exception(f"Error refreshing feeds: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while refreshing feeds: {str(e)}"
            )
    
    def _on_add_feed(self):
        """Show dialog to add a new feed."""
        dialog = RSSFeedDialog(self.db_session, self.rss_manager, parent=self)
        if dialog.exec() == RSSFeedDialog.DialogCode.Accepted:
            # Reload feeds
            self.load_feeds()
    
    def _on_manage_feeds(self):
        """Show dialog to manage feeds."""
        dialog = RSSFeedDialog(self.db_session, self.rss_manager, parent=self)
        if dialog.exec() == RSSFeedDialog.DialogCode.Accepted:
            # Reload feeds
            self.load_feeds()
    
    def _on_feed_selection_changed(self):
        """Handle feed selection change."""
        selected_items = self.feed_table.selectedItems()
        if not selected_items:
            return
            
        feed_item = self.feed_table.item(selected_items[0].row(), 0)
        feed_id = feed_item.data(Qt.ItemDataRole.UserRole)
        
        # Load entries for selected feed
        self.load_feed_entries(feed_id)
    
    def _on_entry_selection_changed(self):
        """Handle entry selection change."""
        selected_items = self.entries_table.selectedItems()
        if not selected_items:
            self.content_preview.clear()
            self.import_btn.setEnabled(False)
            self.view_btn.setEnabled(False)
            return
            
        entry_item = self.entries_table.item(selected_items[0].row(), 0)
        entry_id = entry_item.data(Qt.ItemDataRole.UserRole)
        
        # Load entry content
        entry = self.db_session.query(RSSFeedEntry).get(entry_id)
        if not entry:
            return
            
        # Check if entry is already imported
        if entry.document_id:
            document = self.db_session.query(Document).get(entry.document_id)
            if document:
                self.view_btn.setEnabled(True)
                self.import_btn.setEnabled(False)
            else:
                self.view_btn.setEnabled(False)
                self.import_btn.setEnabled(True)
        else:
            self.view_btn.setEnabled(False)
            self.import_btn.setEnabled(True)
        
        # Show content preview
        content = self.rss_manager.get_entry_content(entry)
        self.content_preview.setHtml(content)
    
    def _on_filter_changed(self):
        """Handle filter combo change."""
        if self.current_feed_id:
            self.load_feed_entries(self.current_feed_id)
    
    def _on_feed_context_menu(self, pos):
        """Show context menu for feed."""
        global_pos = self.feed_table.mapToGlobal(pos)
        row = self.feed_table.rowAt(pos.y())
        
        if row < 0:
            return
            
        feed_item = self.feed_table.item(row, 0)
        feed_id = feed_item.data(Qt.ItemDataRole.UserRole)
        
        menu = QMenu(self)
        
        refresh_action = QAction("Refresh Feed", self)
        refresh_action.triggered.connect(lambda: self._on_refresh_feed(feed_id))
        menu.addAction(refresh_action)
        
        menu.addSeparator()
        
        import_all_action = QAction("Import All Unread", self)
        import_all_action.triggered.connect(lambda: self._on_import_all_unread(feed_id))
        menu.addAction(import_all_action)
        
        menu.addSeparator()
        
        edit_action = QAction("Edit Feed", self)
        edit_action.triggered.connect(lambda: self._on_edit_feed(feed_id))
        menu.addAction(edit_action)
        
        delete_action = QAction("Delete Feed", self)
        delete_action.triggered.connect(lambda: self._on_delete_feed(feed_id))
        menu.addAction(delete_action)
        
        menu.exec(global_pos)
    
    def _on_entry_context_menu(self, pos):
        """Show context menu for entry."""
        global_pos = self.entries_table.mapToGlobal(pos)
        row = self.entries_table.rowAt(pos.y())
        
        if row < 0:
            return
            
        entry_item = self.entries_table.item(row, 0)
        entry_id = entry_item.data(Qt.ItemDataRole.UserRole)
        
        entry = self.db_session.query(RSSFeedEntry).get(entry_id)
        if not entry:
            return
            
        menu = QMenu(self)
        
        # Different options based on whether entry is imported
        if entry.document_id:
            document = self.db_session.query(Document).get(entry.document_id)
            if document:
                view_action = QAction("View Document", self)
                view_action.triggered.connect(lambda: self._on_view_document(document.id))
                menu.addAction(view_action)
            else:
                import_action = QAction("Import Again", self)
                import_action.triggered.connect(lambda: self._on_import_entry(entry_id))
                menu.addAction(import_action)
        else:
            import_action = QAction("Import Entry", self)
            import_action.triggered.connect(lambda: self._on_import_entry(entry_id))
            menu.addAction(import_action)
        
        menu.addSeparator()
        
        mark_read_action = QAction("Mark as Read", self)
        mark_read_action.triggered.connect(lambda: self._on_mark_read(entry_id))
        menu.addAction(mark_read_action)
        
        mark_unread_action = QAction("Mark as Unread", self)
        mark_unread_action.triggered.connect(lambda: self._on_mark_unread(entry_id))
        menu.addAction(mark_unread_action)
        
        menu.exec(global_pos)
    
    def _on_refresh_feed(self, feed_id):
        """Refresh a specific feed."""
        try:
            feed = self.db_session.query(RSSFeed).get(feed_id)
            if not feed:
                return
                
            self.rss_manager.update_feed(feed)
            
            # Reload feed entries
            self.load_feed_entries(feed_id)
            
            # Update feed list
            self.load_feeds()
            
        except Exception as e:
            logger.exception(f"Error refreshing feed: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while refreshing the feed: {str(e)}"
            )
    
    def _on_edit_feed(self, feed_id):
        """Edit a feed."""
        feed = self.db_session.query(RSSFeed).get(feed_id)
        if not feed:
            return
            
        dialog = RSSFeedDialog(self.db_session, self.rss_manager, parent=self)
        if dialog.exec() == RSSFeedDialog.DialogCode.Accepted:
            # Reload feeds
            self.load_feeds()
            
            # If this was the current feed, reload its entries
            if feed_id == self.current_feed_id:
                self.load_feed_entries(feed_id)
    
    def _on_delete_feed(self, feed_id):
        """Delete a feed."""
        try:
            feed = self.db_session.query(RSSFeed).get(feed_id)
            if not feed:
                return
                
            # Confirm deletion
            if QMessageBox.question(
                self, "Confirm Deletion",
                f"Are you sure you want to delete the feed '{feed.title}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
                
            # Delete feed
            self.db_session.delete(feed)
            self.db_session.commit()
            
            # Reload feeds
            self.load_feeds()
            
            # Clear if this was the current feed
            if feed_id == self.current_feed_id:
                self.current_feed_id = None
                self.entries_table.setRowCount(0)
                self.content_preview.clear()
                self.entries_label.setText("Entries")
                
        except Exception as e:
            logger.exception(f"Error deleting feed: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while deleting the feed: {str(e)}"
            )
    
    def _on_import_entry(self, entry_id):
        """Import an entry as a document."""
        try:
            entry = self.db_session.query(RSSFeedEntry).get(entry_id)
            if not entry:
                return
                
            # Import entry
            document_id = self.rss_manager.import_entry(entry)
            
            if document_id:
                QMessageBox.information(
                    self, "Entry Imported", 
                    "The entry has been imported as a document."
                )
                
                # Reload entries
                if self.current_feed_id:
                    self.load_feed_entries(self.current_feed_id)
                    
                # Enable view button and disable import button
                self.view_btn.setEnabled(True)
                self.import_btn.setEnabled(False)
                
            else:
                QMessageBox.warning(
                    self, "Import Failed", 
                    "Failed to import the entry. Please try again."
                )
                
        except Exception as e:
            logger.exception(f"Error importing entry: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while importing the entry: {str(e)}"
            )
    
    def _on_import_all_unread(self, feed_id):
        """Import all unread entries for a feed."""
        try:
            feed = self.db_session.query(RSSFeed).get(feed_id)
            if not feed:
                return
                
            # Get unread entries
            unread_entries = self.rss_manager.get_unread_entries(feed_id)
            
            if not unread_entries:
                QMessageBox.information(
                    self, "No Unread Entries", 
                    "There are no unread entries to import."
                )
                return
                
            # Confirm import
            if QMessageBox.question(
                self, "Confirm Import",
                f"Are you sure you want to import all {len(unread_entries)} unread entries?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
                
            # Import entries
            imported_count = 0
            for entry in unread_entries:
                document_id = self.rss_manager.import_entry(entry)
                if document_id:
                    imported_count += 1
            
            # Show result
            QMessageBox.information(
                self, "Import Complete", 
                f"Successfully imported {imported_count} out of {len(unread_entries)} entries."
            )
            
            # Reload entries
            if self.current_feed_id:
                self.load_feed_entries(self.current_feed_id)
                
        except Exception as e:
            logger.exception(f"Error importing all unread entries: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred while importing entries: {str(e)}"
            )
    
    def _on_mark_read(self, entry_id):
        """Mark an entry as read."""
        try:
            entry = self.db_session.query(RSSFeedEntry).get(entry_id)
            if not entry:
                return
                
            # Mark as read
            self.rss_manager.mark_entry_read(entry)
            
            # Reload entries
            if self.current_feed_id:
                self.load_feed_entries(self.current_feed_id)
                
        except Exception as e:
            logger.exception(f"Error marking entry as read: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _on_mark_unread(self, entry_id):
        """Mark an entry as unread."""
        try:
            entry = self.db_session.query(RSSFeedEntry).get(entry_id)
            if not entry:
                return
                
            # Mark as unread
            self.rss_manager.mark_entry_unread(entry)
            
            # Reload entries
            if self.current_feed_id:
                self.load_feed_entries(self.current_feed_id)
                
        except Exception as e:
            logger.exception(f"Error marking entry as unread: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred: {str(e)}"
            )
    
    def _on_import_current(self):
        """Import the currently selected entry."""
        selected_items = self.entries_table.selectedItems()
        if not selected_items:
            return
            
        entry_item = self.entries_table.item(selected_items[0].row(), 0)
        entry_id = entry_item.data(Qt.ItemDataRole.UserRole)
        
        self._on_import_entry(entry_id)
    
    def _on_view_current(self):
        """View the document for the currently selected entry."""
        selected_items = self.entries_table.selectedItems()
        if not selected_items:
            return
            
        entry_item = self.entries_table.item(selected_items[0].row(), 0)
        entry_id = entry_item.data(Qt.ItemDataRole.UserRole)
        
        entry = self.db_session.query(RSSFeedEntry).get(entry_id)
        if entry and entry.document_id:
            self._on_view_document(entry.document_id)
    
    def _on_view_document(self, document_id):
        """Open a document."""
        self.open_document_signal.emit(document_id) 