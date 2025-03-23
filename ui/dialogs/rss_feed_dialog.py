# ui/dialogs/rss_feed_dialog.py

import logging
from typing import Optional, List, Dict, Any

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QFormLayout, QLineEdit, QSpinBox, QCheckBox, QComboBox,
    QDialogButtonBox, QMessageBox, QGroupBox, QHeaderView,
    QAbstractItemView, QMenu, QStyleFactory
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint
from PyQt6.QtGui import QAction

from core.knowledge_base.models import RSSFeed, Category, RSSFeedEntry
from core.utils.rss_feed_manager import RSSFeedManager
from core.utils.category_helper import get_all_categories, populate_category_combo

logger = logging.getLogger(__name__)

class AddEditFeedDialog(QDialog):
    """Dialog for adding or editing an RSS feed."""
    
    def __init__(self, db_session, rss_manager: RSSFeedManager, feed: Optional[RSSFeed] = None, parent=None):
        """
        Initialize the dialog.
        
        Args:
            db_session: Database session
            rss_manager: RSS feed manager instance
            feed: Optional RSS feed to edit (None for new feed)
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.db_session = db_session
        self.rss_manager = rss_manager
        self.feed = feed
        self.result_feed = None  # Will store the created/updated feed
        
        # Set window properties
        self.setWindowTitle("Add RSS Feed" if feed is None else "Edit RSS Feed")
        self.setMinimumWidth(500)
        
        # Create UI
        self._create_ui()
        
        # Load data if editing existing feed
        if feed:
            self._load_feed_data()
    
    def _create_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Feed properties
        form_layout = QFormLayout()
        
        # Title
        self.title_input = QLineEdit()
        form_layout.addRow("Title:", self.title_input)
        
        # URL
        self.url_input = QLineEdit()
        form_layout.addRow("Feed URL:", self.url_input)
        
        # Category
        self.category_combo = QComboBox()
        self.category_combo.addItem("None", None)
        self._populate_categories()
        form_layout.addRow("Category:", self.category_combo)
        
        # Update frequency
        self.frequency_spin = QSpinBox()
        self.frequency_spin.setRange(5, 1440)  # 5 minutes to 24 hours
        self.frequency_spin.setValue(60)  # Default: 1 hour
        self.frequency_spin.setSuffix(" minutes")
        form_layout.addRow("Check frequency:", self.frequency_spin)
        
        # Auto import
        self.auto_import_check = QCheckBox("Automatically import new items")
        self.auto_import_check.setChecked(True)
        form_layout.addRow("", self.auto_import_check)
        
        # Max items to keep
        self.max_items_spin = QSpinBox()
        self.max_items_spin.setRange(0, 1000)  # 0 = keep all
        self.max_items_spin.setValue(50)
        self.max_items_spin.setSpecialValueText("Keep all")  # For value 0
        form_layout.addRow("Max items to keep:", self.max_items_spin)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        
        # Add test button
        test_button = QPushButton("Test Feed")
        test_button.clicked.connect(self._on_test_feed)
        button_box.addButton(test_button, QDialogButtonBox.ButtonRole.ActionRole)
        
        layout.addWidget(button_box)
    
    def _populate_categories(self):
        """Populate the category combo box."""
        try:
            from core.utils.category_helper import populate_category_combo
            # No "All Categories" option for RSS feed dialog
            populate_category_combo(self.category_combo, self.db_session, include_all_option=False)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to populate categories: {e}")
            
            # Fallback: Get categories directly from database
            categories = self.db_session.query(Category).order_by(Category.name).all()
            for category in categories:
                self.category_combo.addItem(category.name, category.id)
    
    def _load_feed_data(self):
        """Load data from the feed being edited."""
        if not self.feed:
            return
        
        self.title_input.setText(self.feed.title)
        self.url_input.setText(self.feed.url)
        
        # Set category
        if self.feed.category_id:
            index = self.category_combo.findData(self.feed.category_id)
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
        
        self.frequency_spin.setValue(self.feed.check_frequency)
        self.auto_import_check.setChecked(self.feed.auto_import)
        self.max_items_spin.setValue(self.feed.max_items_to_keep)
    
    @pyqtSlot()
    def _on_test_feed(self):
        """Test the feed URL."""
        url = self.url_input.text().strip()
        
        if not url:
            QMessageBox.warning(
                self, "Invalid URL", 
                "Please enter a valid RSS feed URL."
            )
            return
        
        try:
            # Use feedparser to validate and get feed info
            import feedparser
            
            # Show message that we're testing
            QMessageBox.information(
                self, "Testing Feed", 
                "Testing feed URL. This may take a moment..."
            )
            
            parsed = feedparser.parse(url)
            
            if not parsed or not hasattr(parsed, 'feed') or not hasattr(parsed.feed, 'title'):
                QMessageBox.warning(
                    self, "Invalid Feed", 
                    f"The URL does not appear to be a valid RSS feed: {url}"
                )
                return
            
            # Update title if the user hasn't set one yet
            if not self.title_input.text() and hasattr(parsed.feed, 'title'):
                self.title_input.setText(parsed.feed.title)
            
            # Show success message with feed info
            entry_count = len(parsed.entries) if hasattr(parsed, 'entries') else 0
            
            QMessageBox.information(
                self, "Valid RSS Feed", 
                f"Successfully parsed RSS feed:\n\n"
                f"Title: {parsed.feed.title}\n"
                f"Entries: {entry_count}\n\n"
                f"This feed can be used with Incrementum."
            )
            
        except Exception as e:
            logger.exception(f"Error testing feed: {e}")
            QMessageBox.critical(
                self, "Error", 
                f"Error testing feed: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_accept(self):
        """Handle accept button click."""
        # Validate inputs
        title = self.title_input.text().strip()
        url = self.url_input.text().strip()
        
        if not title:
            QMessageBox.warning(
                self, "Missing Title", 
                "Please enter a title for the feed."
            )
            return
        
        if not url:
            QMessageBox.warning(
                self, "Missing URL", 
                "Please enter the URL for the feed."
            )
            return
        
        # Get other values
        category_id = self.category_combo.currentData()
        check_frequency = self.frequency_spin.value()
        auto_import = self.auto_import_check.isChecked()
        max_items = self.max_items_spin.value()
        
        try:
            if self.feed:  # Editing existing feed
                # Update feed properties
                self.feed.title = title
                self.feed.url = url
                self.feed.category_id = category_id
                self.feed.check_frequency = check_frequency
                self.feed.auto_import = auto_import
                self.feed.max_items_to_keep = max_items
                
                # Save changes
                self.db_session.commit()
                self.result_feed = self.feed
                
            else:  # Adding new feed
                # Create new feed
                new_feed = RSSFeed(
                    title=title,
                    url=url,
                    category_id=category_id,
                    check_frequency=check_frequency,
                    auto_import=auto_import,
                    max_items_to_keep=max_items
                )
                
                self.db_session.add(new_feed)
                self.db_session.commit()
                
                # Initial update to get entries
                self.rss_manager.update_feed(new_feed)
                
                self.result_feed = new_feed
            
            # Close dialog
            self.accept()
            
        except Exception as e:
            logger.exception(f"Error saving feed: {e}")
            self.db_session.rollback()
            
            QMessageBox.critical(
                self, "Error", 
                f"Error saving feed: {str(e)}"
            )

class RSSFeedDialog(QDialog):
    """Dialog for managing RSS feeds."""
    
    feedsUpdated = pyqtSignal()
    
    def __init__(self, db_session, rss_manager: RSSFeedManager, parent=None):
        """
        Initialize the dialog.
        
        Args:
            db_session: Database session
            rss_manager: RSS feed manager instance
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.db_session = db_session
        self.rss_manager = rss_manager
        
        # Set window properties
        self.setWindowTitle("Manage RSS Feeds")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        
        # Create UI
        self._create_ui()
        
        # Load feeds
        self._load_feeds()
    
    def _create_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Feed list section
        feed_group = QGroupBox("RSS Feeds")
        feed_layout = QVBoxLayout(feed_group)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.add_button = QPushButton("Add Feed")
        self.add_button.clicked.connect(self._on_add_feed)
        toolbar_layout.addWidget(self.add_button)
        
        self.refresh_button = QPushButton("Refresh All")
        self.refresh_button.clicked.connect(self._on_refresh_feeds)
        toolbar_layout.addWidget(self.refresh_button)
        
        self.import_button = QPushButton("Import New Items")
        self.import_button.clicked.connect(self._on_import_all)
        toolbar_layout.addWidget(self.import_button)
        
        toolbar_layout.addStretch()
        
        feed_layout.addLayout(toolbar_layout)
        
        # Feed table
        self.feed_table = QTableWidget()
        self.feed_table.setColumnCount(6)
        self.feed_table.setHorizontalHeaderLabels([
            "Title", "URL", "Category", "Last Updated", "Auto Import", "Entry Count"
        ])
        self.feed_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.feed_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.feed_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.feed_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.feed_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.feed_table.customContextMenuRequested.connect(self._on_feed_context_menu)
        feed_layout.addWidget(self.feed_table)
        
        layout.addWidget(feed_group, 3)
        
        # Entries section
        entry_group = QGroupBox("Feed Entries")
        entry_layout = QVBoxLayout(entry_group)
        
        self.entry_table = QTableWidget()
        self.entry_table.setColumnCount(4)
        self.entry_table.setHorizontalHeaderLabels(["Title", "Published", "Processed", "Document"])
        self.entry_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.entry_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.entry_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        entry_layout.addWidget(self.entry_table)
        
        layout.addWidget(entry_group, 2)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Connect selection change
        self.feed_table.itemSelectionChanged.connect(self._on_feed_selection_changed)
    
    def _load_feeds(self):
        """Load feeds into the table."""
        self.feed_table.setRowCount(0)
        
        feeds = self.rss_manager.get_all_feeds()
        
        for row, feed in enumerate(feeds):
            self.feed_table.insertRow(row)
            
            # Title
            title_item = QTableWidgetItem(feed.title)
            title_item.setData(Qt.ItemDataRole.UserRole, feed.id)
            self.feed_table.setItem(row, 0, title_item)
            
            # URL
            url_item = QTableWidgetItem(feed.url)
            self.feed_table.setItem(row, 1, url_item)
            
            # Category
            category_name = feed.category.name if feed.category else "None"
            category_item = QTableWidgetItem(category_name)
            self.feed_table.setItem(row, 2, category_item)
            
            # Last updated
            last_updated = feed.last_checked.strftime("%Y-%m-%d %H:%M") if feed.last_checked else "Never"
            last_updated_item = QTableWidgetItem(last_updated)
            self.feed_table.setItem(row, 3, last_updated_item)
            
            # Auto import
            auto_import_item = QTableWidgetItem("Yes" if feed.auto_import else "No")
            self.feed_table.setItem(row, 4, auto_import_item)
            
            # Entry count
            entry_count = len(feed.entries) if hasattr(feed, 'entries') else 0
            entry_count_item = QTableWidgetItem(str(entry_count))
            self.feed_table.setItem(row, 5, entry_count_item)
        
        if feeds:
            self.feed_table.selectRow(0)
    
    def _load_feed_entries(self, feed_id: int):
        """Load entries for a selected feed."""
        self.entry_table.setRowCount(0)
        
        # Get feed entries - using proper query with RSSFeedEntry model
        entries = self.db_session.query(
            RSSFeedEntry
        ).filter(
            RSSFeedEntry.feed_id == feed_id
        ).order_by(RSSFeedEntry.publish_date.desc()).all()
        
        if not entries:
            return
        
        for row, entry in enumerate(entries):
            self.entry_table.insertRow(row)
            
            # Title
            title_item = QTableWidgetItem(entry.title)
            title_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.entry_table.setItem(row, 0, title_item)
            
            # Published date
            published = entry.publish_date.strftime("%Y-%m-%d %H:%M") if entry.publish_date else "Unknown"
            published_item = QTableWidgetItem(published)
            self.entry_table.setItem(row, 1, published_item)
            
            # Processed
            processed_item = QTableWidgetItem("Yes" if entry.processed else "No")
            self.entry_table.setItem(row, 2, processed_item)
            
            # Document link
            document = "View" if entry.document_id else "Not imported"
            document_item = QTableWidgetItem(document)
            document_item.setData(Qt.ItemDataRole.UserRole, entry.document_id)
            self.entry_table.setItem(row, 3, document_item)
    
    @pyqtSlot()
    def _on_feed_selection_changed(self):
        """Handle feed selection change."""
        selected_rows = self.feed_table.selectedItems()
        if not selected_rows:
            self.entry_table.setRowCount(0)
            return
        
        # Get feed ID from first column
        feed_id = self.feed_table.item(selected_rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        if feed_id:
            self._load_feed_entries(feed_id)
    
    @pyqtSlot()
    def _on_add_feed(self):
        """Handle add feed button click."""
        dialog = AddEditFeedDialog(self.db_session, self.rss_manager, parent=self)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted and dialog.result_feed:
            self._load_feeds()
            self.feedsUpdated.emit()
    
    @pyqtSlot(QPoint)
    def _on_feed_context_menu(self, pos):
        """Show context menu for feed table."""
        selected_rows = self.feed_table.selectedItems()
        if not selected_rows:
            return
        
        # Get feed ID from first column
        row = selected_rows[0].row()
        feed_id = self.feed_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        
        # Create context menu
        menu = QMenu(self)
        
        edit_action = menu.addAction("Edit Feed")
        edit_action.triggered.connect(lambda: self._on_edit_feed(feed_id))
        
        delete_action = menu.addAction("Delete Feed")
        delete_action.triggered.connect(lambda: self._on_delete_feed(feed_id))
        
        menu.addSeparator()
        
        refresh_action = menu.addAction("Refresh Feed")
        refresh_action.triggered.connect(lambda: self._on_refresh_feed(feed_id))
        
        import_action = menu.addAction("Import New Items")
        import_action.triggered.connect(lambda: self._on_import_feed(feed_id))
        
        # Show menu
        menu.exec(self.feed_table.viewport().mapToGlobal(pos))
    
    def _on_edit_feed(self, feed_id: int):
        """Handle edit feed action."""
        feed = self.db_session.query(RSSFeed).get(feed_id)
        if not feed:
            return
        
        dialog = AddEditFeedDialog(self.db_session, self.rss_manager, feed, parent=self)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            self._load_feeds()
            self.feedsUpdated.emit()
    
    def _on_delete_feed(self, feed_id: int):
        """Handle delete feed action."""
        feed = self.db_session.query(RSSFeed).get(feed_id)
        if not feed:
            return
        
        # Confirm deletion
        result = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete the feed '{feed.title}'?\n\n"
            f"This will remove all feed information from the database.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if result != QMessageBox.StandardButton.Yes:
            return
        
        # Ask if documents should also be deleted
        delete_docs_result = QMessageBox.question(
            self, "Delete Documents",
            f"Do you also want to delete all documents imported from this feed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        delete_documents = (delete_docs_result == QMessageBox.StandardButton.Yes)
        
        # Delete feed
        success = self.rss_manager.delete_feed(feed_id, delete_documents)
        
        if success:
            self._load_feeds()
            self.feedsUpdated.emit()
            
            QMessageBox.information(
                self, "Feed Deleted",
                f"The feed '{feed.title}' has been deleted."
            )
        else:
            QMessageBox.critical(
                self, "Error",
                f"An error occurred while deleting the feed."
            )
    
    def _on_refresh_feed(self, feed_id: int):
        """Handle refresh feed action."""
        feed = self.db_session.query(RSSFeed).get(feed_id)
        if not feed:
            return
        
        try:
            new_entries = self.rss_manager.update_feed(feed)
            
            QMessageBox.information(
                self, "Feed Updated",
                f"Feed '{feed.title}' updated successfully.\n\n"
                f"{len(new_entries)} new entries found."
            )
            
            self._load_feeds()
            self._load_feed_entries(feed_id)
            self.feedsUpdated.emit()
            
        except Exception as e:
            logger.exception(f"Error refreshing feed: {e}")
            
            QMessageBox.critical(
                self, "Error",
                f"An error occurred while refreshing the feed: {str(e)}"
            )
    
    def _on_import_feed(self, feed_id: int):
        """Handle import feed entries action."""
        feed = self.db_session.query(RSSFeed).get(feed_id)
        if not feed:
            return
        
        try:
            imported_docs = self.rss_manager.import_new_entries(feed)
            
            QMessageBox.information(
                self, "Items Imported",
                f"Successfully imported {len(imported_docs)} new items from feed '{feed.title}'."
            )
            
            self._load_feeds()
            self._load_feed_entries(feed_id)
            self.feedsUpdated.emit()
            
        except Exception as e:
            logger.exception(f"Error importing feed entries: {e}")
            
            QMessageBox.critical(
                self, "Error",
                f"An error occurred while importing feed entries: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_refresh_feeds(self):
        """Handle refresh all feeds button click."""
        try:
            # Show progress message
            QMessageBox.information(
                self, "Refreshing Feeds",
                "Refreshing all feeds. This may take some time..."
            )
            
            result = self.rss_manager.update_all_feeds()
            
            # Count total new entries
            total_entries = sum(len(entries) for entries in result.values())
            
            QMessageBox.information(
                self, "Feeds Updated",
                f"All feeds have been updated successfully.\n\n"
                f"{total_entries} new entries found."
            )
            
            self._load_feeds()
            self.feedsUpdated.emit()
            
        except Exception as e:
            logger.exception(f"Error refreshing feeds: {e}")
            
            QMessageBox.critical(
                self, "Error",
                f"An error occurred while refreshing feeds: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_import_all(self):
        """Handle import all new items button click."""
        try:
            # Show progress message
            QMessageBox.information(
                self, "Importing Items",
                "Importing all new items. This may take some time..."
            )
            
            result = self.rss_manager.import_all_new_entries()
            
            # Count total imported documents
            total_docs = sum(len(docs) for docs in result.values())
            
            QMessageBox.information(
                self, "Items Imported",
                f"Successfully imported {total_docs} new items from all feeds."
            )
            
            self._load_feeds()
            self.feedsUpdated.emit()
            
        except Exception as e:
            logger.exception(f"Error importing new items: {e}")
            
            QMessageBox.critical(
                self, "Error",
                f"An error occurred while importing new items: {str(e)}"
            ) 