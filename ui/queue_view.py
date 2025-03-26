# ui/queue_view.py

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QComboBox, QFormLayout, QSpinBox, QSplitter,
    QMessageBox, QMenu, QCheckBox, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QApplication, QStyle, QSizePolicy, QDockWidget, QMainWindow, QLineEdit, QTextBrowser,
    QInputDialog, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QPoint, QModelIndex
from PyQt6.QtGui import QIcon, QAction, QColor, QBrush, QKeySequence, QShortcut, QPalette, QFont

from core.knowledge_base.models import Document, Category, Extract, IncrementalReading
from core.spaced_repetition import FSRSAlgorithm
from core.utils.settings_manager import SettingsManager
from core.utils.shortcuts import ShortcutManager
from core.utils.category_helper import get_all_categories, populate_category_combo

logger = logging.getLogger(__name__)

class QueueView(QWidget):
    """Widget for managing the document reading queue."""
    
    documentSelected = pyqtSignal(int)  # document_id
    
    def __init__(self, db_session, settings_manager=None):
        """Initialize with database session and settings.
        
        Args:
            db_session: SQLAlchemy database session
            settings_manager: Settings manager instance
        """
        super().__init__()
        
        # Set object name to allow this widget to be found by MainWindow
        self.setObjectName("queue_view")
        
        self.db_session = db_session
        self.settings_manager = settings_manager or SettingsManager()
        
        # Initialize FSRS with algorithm settings from the settings manager
        fsrs_params = self._get_fsrs_params()
        self.fsrs = FSRSAlgorithm(db_session, params=fsrs_params)
        
        # Create UI
        self._create_ui()
        
        # Initialize theme from settings
        self._initialize_theme()
        
        # Set up keyboard shortcuts
        self._setup_shortcuts()
        
        # Set up drag and drop
        self._setup_queue_drag_drop()
        
        # Load initial data
        self._load_queue_data()
        
        # Load knowledge tree
        self._load_knowledge_tree()
        
        # Restore UI state from settings
        self.restoreState()
    
    def _get_fsrs_params(self) -> Dict[str, Any]:
        """Get FSRS algorithm parameters from settings."""
        if not self.settings_manager:
            return None
            
        # Get algorithm settings
        min_interval = self.settings_manager.get_setting("algorithm", "minimum_interval", 1)
        max_interval = self.settings_manager.get_setting("algorithm", "maximum_interval", 3650)
        interval_modifier = self.settings_manager.get_setting("algorithm", "interval_modifier", 1.0)
        target_retention = self.settings_manager.get_setting("algorithm", "target_retention", 0.9)
        
        # Create params dictionary with only the settings that should override defaults
        params = {
            "MIN_INTERVAL": min_interval,
            "MAX_INTERVAL": max_interval,
            "R_TARGET": target_retention,
        }
        
        return params
    
    def _initialize_theme(self):
        """Initialize the UI theme from settings."""
        try:
            if hasattr(self, 'settings_manager') and self.settings_manager:
                # Get saved theme
                theme = self.settings_manager.get_setting('ui', 'theme', 'Default')
                
                # Find theme in combo box
                index = self.theme_combo.findText(theme)
                if index >= 0:
                    # Set the combo box to the saved theme
                    self.theme_combo.setCurrentIndex(index)
                else:
                    # Default to the first theme
                    self.theme_combo.setCurrentIndex(0)
                
                # Apply the theme
                self._apply_theme(self.theme_combo.currentIndex())
        except Exception as e:
            logger.exception(f"Error initializing theme: {e}")

    def _apply_theme(self, index):
        """Apply theme to the entire UI."""
        try:
            # Get the theme name from the combo box
            theme_name = self.theme_combo.itemText(index)
            logger.info(f"Applying theme: {theme_name}")
            
            # Get theme colors
            colors = self._get_theme_colors(theme_name)
            
            # Apply to knowledge tree
            self._apply_tree_theme(theme_name, colors)
            
            # Apply to queue table
            self._apply_queue_theme(theme_name, colors)
            
            # Apply to panels
            self._apply_panel_theme(theme_name, colors)
            
            # Apply general synchronized styling
            self._sync_with_application_palette()
            
            # Save the selected theme
            if hasattr(self, 'settings_manager') and self.settings_manager:
                # Check if we need to update the settings manager
                current_theme = self.settings_manager.get_setting('ui', 'theme', 'Default')
                if current_theme != theme_name.lower() or theme_name == "Custom":
                    logger.debug(f"Saving theme selection: {theme_name}")
                    self.settings_manager.set_setting('ui', 'theme', theme_name.lower())
                    
                    # If this is the Custom theme, check if we need to set custom_theme flag
                    if theme_name == "Custom" and not self.settings_manager.get_setting('ui', 'custom_theme', False):
                        self.settings_manager.set_setting('ui', 'custom_theme', True)
                    elif theme_name != "Custom" and self.settings_manager.get_setting('ui', 'custom_theme', False):
                        self.settings_manager.set_setting('ui', 'custom_theme', False)
                    
        except Exception as e:
            logger.exception(f"Error applying theme: {e}")
        
    def _get_theme_colors(self, theme_name):
        """Get color scheme for the selected theme."""
        colors = {
            'background': None,
            'foreground': None,
            'border': None,
            'header_background': None,
            'header_foreground': None,
            'item_background': None,
            'selection_background': None,
            'selection_foreground': None,
            'alternate_background': None,
        }
        
        # Check if we have a theme_manager in settings_manager
        theme_from_manager = None
        if hasattr(self, 'settings_manager') and hasattr(self.settings_manager, 'theme_manager'):
            try:
                # Try to get theme from the theme manager
                theme_from_manager = self.settings_manager.theme_manager.get_theme(theme_name.lower())
            except Exception as e:
                logger.debug(f"Could not get theme from theme_manager: {e}")
        
        # If we got a theme from the theme manager, use it
        if theme_from_manager:
            try:
                colors['background'] = theme_from_manager.get('background', "#FFFFFF")
                colors['foreground'] = theme_from_manager.get('foreground', "#000000")
                colors['border'] = theme_from_manager.get('border', "#CCCCCC")
                colors['header_background'] = theme_from_manager.get('header_background', "#E5E5E5")
                colors['header_foreground'] = theme_from_manager.get('header_foreground', "#000000")
                colors['selection_background'] = theme_from_manager.get('selection_background', "#CCE8FF")
                colors['selection_foreground'] = theme_from_manager.get('selection_foreground', "#000000")
                colors['alternate_background'] = theme_from_manager.get('alternate_background', "#F0F0F0")
                colors['item_background'] = theme_from_manager.get('item_background', colors['background'])
                return colors
            except Exception as e:
                logger.warning(f"Error processing theme from theme_manager: {e}")
        
        # Default theme uses system colors
        if theme_name == "Default":
            # Get system palette
            palette = QApplication.palette()
            colors['background'] = palette.color(QPalette.ColorRole.Base).name()
            colors['foreground'] = palette.color(QPalette.ColorRole.Text).name()
            colors['border'] = palette.color(QPalette.ColorRole.Mid).name()
            colors['header_background'] = palette.color(QPalette.ColorRole.Button).name()
            colors['header_foreground'] = palette.color(QPalette.ColorRole.ButtonText).name()
            colors['selection_background'] = palette.color(QPalette.ColorRole.Highlight).name()
            colors['selection_foreground'] = palette.color(QPalette.ColorRole.HighlightedText).name()
            colors['alternate_background'] = palette.color(QPalette.ColorRole.AlternateBase).name()
            colors['item_background'] = colors['background']
            
        # Dark theme
        elif theme_name == "Dark":
            colors['background'] = "#2D2D30"
            colors['foreground'] = "#E6E6E6"
            colors['border'] = "#3F3F46"
            colors['header_background'] = "#252526"
            colors['header_foreground'] = "#E6E6E6"
            colors['item_background'] = "#2D2D30"
            colors['selection_background'] = "#007ACC"
            colors['selection_foreground'] = "#FFFFFF"
            colors['alternate_background'] = "#252526"
            
        # Light theme
        elif theme_name == "Light":
            colors['background'] = "#F5F5F5"
            colors['foreground'] = "#1E1E1E"
            colors['border'] = "#CCCCCC"
            colors['header_background'] = "#E5E5E5"
            colors['header_foreground'] = "#1E1E1E"
            colors['item_background'] = "#FFFFFF"
            colors['selection_background'] = "#CCE8FF"
            colors['selection_foreground'] = "#1E1E1E"
            colors['alternate_background'] = "#EAEAEA"
            
        # SuperMemo theme
        elif theme_name == "SuperMemo":
            colors['background'] = "#EEF5FD"
            colors['foreground'] = "#000000"
            colors['border'] = "#94BADE"
            colors['header_background'] = "#D6E9FF"
            colors['header_foreground'] = "#000000"
            colors['item_background'] = "#EEF5FD"
            colors['selection_background'] = "#FFD700"  # Gold for selection
            colors['selection_foreground'] = "#000000"
            colors['alternate_background'] = "#E5EFF9"
            
        # Custom theme (from settings)
        elif theme_name == "Custom":
            # Try to get colors from theme_file if it exists
            if hasattr(self, 'settings_manager'):
                theme_file = self.settings_manager.get_setting('ui', 'theme_file', '')
                
                if theme_file and os.path.exists(theme_file):
                    try:
                        # Try to load the theme from the file
                        with open(theme_file, 'r') as f:
                            import json
                            theme_data = json.load(f)
                            
                        # Get colors from theme data
                        colors['background'] = theme_data.get('background', "#FFFFFF")
                        colors['foreground'] = theme_data.get('foreground', "#000000")
                        colors['border'] = theme_data.get('border', "#CCCCCC")
                        colors['header_background'] = theme_data.get('header_background', "#E5E5E5")
                        colors['header_foreground'] = theme_data.get('header_foreground', "#000000")
                        colors['selection_background'] = theme_data.get('selection_background', "#CCE8FF")
                        colors['selection_foreground'] = theme_data.get('selection_foreground', "#000000")
                        colors['alternate_background'] = theme_data.get('alternate_background', "#F0F0F0")
                        colors['item_background'] = theme_data.get('item_background', colors['background'])
                        return colors
                        
                    except Exception as e:
                        logger.warning(f"Error loading custom theme from file: {e}")
                        
                # Fall back to individual settings if theme file didn't work
                colors['background'] = self.settings_manager.get_setting('ui', 'custom_theme_background', "#FFFFFF")
                colors['foreground'] = self.settings_manager.get_setting('ui', 'custom_theme_foreground', "#000000")
                colors['border'] = self.settings_manager.get_setting('ui', 'custom_theme_border', "#CCCCCC")
                colors['header_background'] = self.settings_manager.get_setting('ui', 'custom_theme_header_background', "#E5E5E5")
                colors['header_foreground'] = self.settings_manager.get_setting('ui', 'custom_theme_header_foreground', "#000000")
                colors['selection_background'] = self.settings_manager.get_setting('ui', 'custom_theme_selection_background', "#CCE8FF")
                colors['selection_foreground'] = self.settings_manager.get_setting('ui', 'custom_theme_selection_foreground', "#000000")
                colors['alternate_background'] = self.settings_manager.get_setting('ui', 'custom_theme_alternate_background', "#F0F0F0")
                colors['item_background'] = self.settings_manager.get_setting('ui', 'custom_theme_item_background', colors['background'])
            
        return colors

    def _apply_tree_theme(self, theme_name, colors):
        """Apply theme to the knowledge tree."""
        tree_style = []
        
        # QTreeWidget base styling
        if colors['background']:
            tree_style.append(f"QTreeWidget {{ background-color: {colors['background']}; }}")
        if colors['foreground']:
            tree_style.append(f"QTreeWidget {{ color: {colors['foreground']}; }}")
        if colors['border']:
            tree_style.append(f"QTreeWidget {{ border: 1px solid {colors['border']}; }}")
        
        # QTreeWidget header styling
        if colors['header_background']:
            tree_style.append(f"QHeaderView::section {{ background-color: {colors['header_background']}; }}")
        if colors['header_foreground']:
            tree_style.append(f"QHeaderView::section {{ color: {colors['header_foreground']}; }}")
        if colors['border']:
            tree_style.append(f"QHeaderView::section {{ border: 1px solid {colors['border']}; }}")
        
        # QTreeWidget item styling
        if colors['item_background']:
            tree_style.append(f"QTreeWidget::item {{ background-color: {colors['item_background']}; }}")
        
        # Selection styling
        if colors['selection_background']:
            tree_style.append(f"QTreeWidget::item:selected {{ background-color: {colors['selection_background']}; }}")
        if colors['selection_foreground']:
            tree_style.append(f"QTreeWidget::item:selected {{ color: {colors['selection_foreground']}; }}")
        
        # Alternate row colors
        if colors['alternate_background']:
            tree_style.append(f"QTreeWidget {{ alternate-background-color: {colors['alternate_background']}; }}")
            self.knowledge_tree.setAlternatingRowColors(True)
        else:
            self.knowledge_tree.setAlternatingRowColors(False)
        
        # Apply the composite stylesheet
        self.knowledge_tree.setStyleSheet("\n".join(tree_style))

    def _apply_queue_theme(self, theme_name, colors):
        """Apply theme to the queue table."""
        if not hasattr(self, 'queue_table'):
            return
        
        queue_style = []
        
        # QTreeWidget base styling
        if colors['background']:
            queue_style.append(f"QTreeWidget {{ background-color: {colors['background']}; }}")
        if colors['foreground']:
            queue_style.append(f"QTreeWidget {{ color: {colors['foreground']}; }}")
        if colors['border']:
            queue_style.append(f"QTreeWidget {{ border: 1px solid {colors['border']}; }}")
        
        # QTreeWidget header styling
        if colors['header_background']:
            queue_style.append(f"QHeaderView::section {{ background-color: {colors['header_background']}; }}")
        if colors['header_foreground']:
            queue_style.append(f"QHeaderView::section {{ color: {colors['header_foreground']}; }}")
        if colors['border']:
            queue_style.append(f"QHeaderView::section {{ border: 1px solid {colors['border']}; }}")
        
        # Selection styling
        if colors['selection_background']:
            queue_style.append(f"QTreeWidget::item:selected {{ background-color: {colors['selection_background']}; }}")
        if colors['selection_foreground']:
            queue_style.append(f"QTreeWidget::item:selected {{ color: {colors['selection_foreground']}; }}")
        
        # Alternate row colors
        if colors['alternate_background']:
            queue_style.append(f"QTreeWidget {{ alternate-background-color: {colors['alternate_background']}; }}")
            self.queue_table.setAlternatingRowColors(True)
        else:
            self.queue_table.setAlternatingRowColors(False)
        
        # Apply the composite stylesheet
        self.queue_table.setStyleSheet("\n".join(queue_style))
        
        # Apply to tab widget
        if hasattr(self, 'queue_tabs'):
            tab_style = []
            if colors['background']:
                tab_style.append(f"QTabWidget::pane {{ background-color: {colors['background']}; }}")
            if colors['header_background']:
                tab_style.append(f"QTabBar::tab {{ background-color: {colors['header_background']}; }}")
            if colors['header_foreground']:
                tab_style.append(f"QTabBar::tab {{ color: {colors['header_foreground']}; }}")
            if colors['selection_background']:
                tab_style.append(f"QTabBar::tab:selected {{ background-color: {colors['selection_background']}; }}")
            if colors['selection_foreground']:
                tab_style.append(f"QTabBar::tab:selected {{ color: {colors['selection_foreground']}; }}")
            
            self.queue_tabs.setStyleSheet("\n".join(tab_style))
        
    def _apply_panel_theme(self, theme_name, colors):
        """Apply theme to panels and other elements."""
        panel_style = []
        
        if colors['background']:
            panel_style.append(f"background-color: {colors['background']};")
        if colors['foreground']:
            panel_style.append(f"color: {colors['foreground']};")
        
        # Apply to tree panel
        if hasattr(self, 'tree_panel'):
            self.tree_panel.setStyleSheet(" ".join(panel_style))
        
        # Apply to queue panel
        if hasattr(self, 'queue_panel'):
            self.queue_panel.setStyleSheet(" ".join(panel_style))
        
        # Apply to buttons and other controls
        control_style = []
        
        # Style for buttons
        if colors['background'] and colors['foreground']:
            control_style.append(f"QPushButton {{ background-color: {colors['background']}; color: {colors['foreground']}; }}")
        if colors['selection_background']:
            control_style.append(f"QPushButton:hover {{ background-color: {colors['selection_background']}; }}")
        
        # Style for combo boxes
        if colors['background'] and colors['foreground']:
            control_style.append(f"QComboBox {{ background-color: {colors['background']}; color: {colors['foreground']}; }}")
        
        # Style for checkboxes
        if colors['foreground']:
            control_style.append(f"QCheckBox {{ color: {colors['foreground']}; }}")
        
        # Apply to this widget
        if control_style:
            self.setStyleSheet("\n".join(control_style))

    def _setup_shortcuts(self):
        """Set up keyboard shortcuts for queue navigation and rating."""
        try:
            # Navigate to next document
            next_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
            next_shortcut.activated.connect(self._on_read_next)
            
            # Navigate to previous document
            prev_shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
            prev_shortcut.activated.connect(self._on_read_prev)
            
            # Rate document shortcuts (1-5)
            for rating in range(1, 6):
                rate_shortcut = QShortcut(QKeySequence(f"Ctrl+{rating}"), self)
                rate_shortcut.activated.connect(lambda r=rating: self._rate_current_document(r))
                
            # Refresh queue
            refresh_shortcut = QShortcut(QKeySequence("F5"), self)
            refresh_shortcut.activated.connect(self._on_refresh)
            
            # Toggle tree panel
            toggle_tree_shortcut = QShortcut(QKeySequence("Ctrl+T"), self)
            toggle_tree_shortcut.activated.connect(self._toggle_tree_panel)
            
            logger.debug("Queue view shortcuts configured")
        except Exception as e:
            logger.exception(f"Error setting up shortcuts: {e}")

    def _add_subcategories(self, parent_item, parent_id, show_empty=True, sort_alphabetically=True):
        """Recursively add subcategories to the tree."""
        # Build query for subcategories
        query = self.db_session.query(Category).filter(Category.parent_id == parent_id)
        
        # Apply sorting
        if sort_alphabetically:
            query = query.order_by(Category.name)
        else:
            # Sort by ID (creation order)
            query = query.order_by(Category.id)
        
        subcategories = query.all()
        
        for subcategory in subcategories:
            # Skip categories with no documents if show_empty is False
            if not show_empty:
                doc_count = self._get_category_document_count(subcategory.id, include_subcategories=True)
                if doc_count == 0:
                    continue
                
            # Create tree item
            subcat_item = self._create_category_tree_item(subcategory)
            
            # Add to parent
            parent_item.addChild(subcat_item)
            
            # Recursively add children
            self._add_subcategories(subcat_item, subcategory.id, show_empty, sort_alphabetically)

    def _get_category_document_count(self, category_id, include_subcategories=False):
        """Get the count of documents in a category, optionally including subcategories."""
        if include_subcategories:
            # Get all subcategory IDs
            category_ids = [category_id]
            self._get_subcategory_ids(category_id, category_ids)
            
            # Count documents in this category and all subcategories
            return self.db_session.query(Document).filter(Document.category_id.in_(category_ids)).count()
        else:
            # Count only documents directly in this category
            return self.db_session.query(Document).filter(Document.category_id == category_id).count()

    def _get_bold_font(self):
        """Return a bold font for tree items."""
        font = self.font()
        font.setBold(True)
        return font

    def _get_count_color(self, count):
        """Return a color based on the document count."""
        if count > 100:
            return QBrush(QColor(255, 0, 0))  # Red for large counts
        elif count > 50:
            return QBrush(QColor(255, 128, 0))  # Orange for medium counts
        elif count > 10:
            return QBrush(QColor(0, 128, 0))  # Green for small counts
        else:
            return QBrush(QColor(0, 0, 255))  # Blue for very small counts

    def _expand_all_categories(self):
        """Expand all categories in the knowledge tree."""
        self.knowledge_tree.expandAll()

    def _collapse_all_categories(self):
        """Collapse all categories in the knowledge tree."""
        self.knowledge_tree.collapseAll()
        
        # Keep the top level items expanded
        for i in range(self.knowledge_tree.topLevelItemCount()):
            self.knowledge_tree.topLevelItem(i).setExpanded(True)

    def _on_tree_search(self):
        """Search for categories in the knowledge tree."""
        search_text = self.tree_search_box.currentText().strip()
        if not search_text:
            return
            
        # Add to search history if not already there
        if self.tree_search_box.findText(search_text) == -1:
            self.tree_search_box.addItem(search_text)
        
        # Reset any previous search highlighting
        self._reset_tree_highlighting()
        
        # Perform the search
        found_items = []
        self._search_tree_items(self.knowledge_tree.invisibleRootItem(), search_text.lower(), found_items)
        
        if found_items:
            # Highlight found items
            for item in found_items:
                # Set background color for the item
                item.setBackground(0, QBrush(QColor(255, 255, 0, 100)))  # Light yellow highlight
                
                # Ensure all parent items are expanded so the item is visible
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
                    
            # Select and scroll to the first found item
            self.knowledge_tree.setCurrentItem(found_items[0])
            self.knowledge_tree.scrollToItem(found_items[0])
            
            # Update status with count of matches
            QMessageBox.information(self, "Search Results", f"Found {len(found_items)} matching categories.")
        else:
            QMessageBox.information(self, "Search Results", "No matching categories found.")

    def _search_tree_items(self, parent_item, search_text, found_items):
        """Recursively search for items in the tree that match the search text."""
        # Check all children of this item
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child:
                # Check if this item matches
                if search_text in child.text(0).lower():
                    found_items.append(child)
                    
                # Recursively check its children
                self._search_tree_items(child, search_text, found_items)

    def _reset_tree_highlighting(self):
        """Reset the highlighting in the knowledge tree."""
        def reset_item_and_children(item):
            # Reset this item's background
            item.setBackground(0, QBrush())
            
            # Reset all child items
            for i in range(item.childCount()):
                child = item.child(i)
                if child:
                    reset_item_and_children(child)
        
        # Reset all top-level items and their children
        for i in range(self.knowledge_tree.topLevelItemCount()):
            top_item = self.knowledge_tree.topLevelItem(i)
            if top_item:
                reset_item_and_children(top_item)

    def _clear_tree_search(self):
        """Clear the search results and reset the tree."""
        self.tree_search_box.setCurrentText("")
        self._reset_tree_highlighting()

    def _on_tree_filter_changed(self):
        """Handle changes to the tree filter options."""
        # Reload the knowledge tree with the new filter settings
        self._load_knowledge_tree()

    def _rename_category_tree_item(self, item):
        """Rename a category in the tree."""
        if not item:
            return
            
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        if category_id is None:
            QMessageBox.warning(self, "Cannot Rename", "The 'All Categories' item cannot be renamed.")
            return
            
        # Get the category from the database
        category = self.db_session.query(Category).get(category_id)
        if not category:
            QMessageBox.warning(self, "Error", "Category not found in database.")
            return
            
        # Ask for new name
        from PyQt6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "Rename Category", "Enter new category name:",
            text=category.name
        )
        
        if ok and new_name and new_name != category.name:
            # Update category name in database
            category.name = new_name
            self.db_session.commit()
            
            # Update item in tree
            item.setText(0, new_name)
            
            # Show success message
            QMessageBox.information(self, "Success", f"Category renamed to '{new_name}'.")

    def _add_subcategory(self, parent_id):
        """Add a subcategory to the specified parent category."""
        try:
            from PyQt6.QtWidgets import QInputDialog
            
            # Ask for category name
            category_name, ok = QInputDialog.getText(
                self, "New Subcategory", "Enter subcategory name:"
            )
            
            if ok and category_name:
                # Create new category in database with the specified parent
                new_category = Category(name=category_name, parent_id=parent_id)
                self.db_session.add(new_category)
                self.db_session.commit()
                
                # Refresh knowledge tree
                self._load_knowledge_tree()
                
                # Show success message
                QMessageBox.information(
                    self, "Success", 
                    f"Subcategory '{category_name}' created successfully."
                )
        except Exception as e:
            logger.exception(f"Error creating subcategory: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error creating subcategory: {str(e)}"
            )
            # Rollback in case of error
            self.db_session.rollback()

    def _export_category_structure(self):
        """Export the category structure to a JSON file."""
        try:
            from PyQt6.QtWidgets import QFileDialog
            import json
            
            # Ask for file location
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Category Structure", "", "JSON Files (*.json)"
            )
            
            if not file_path:
                return
                
            # If no extension provided, add .json
            if not file_path.endswith('.json'):
                file_path += '.json'
                
            # Get all categories
            categories = self.db_session.query(Category).all()
            
            # Create a dictionary structure
            category_data = []
            for category in categories:
                cat_dict = {
                    'id': category.id,
                    'name': category.name,
                    'parent_id': category.parent_id
                }
                if hasattr(category, 'description') and category.description:
                    cat_dict['description'] = category.description
                    
                category_data.append(cat_dict)
                
            # Write to file
            with open(file_path, 'w') as f:
                json.dump({'categories': category_data}, f, indent=2)
                
            QMessageBox.information(
                self, "Export Successful", 
                f"Category structure exported to {file_path}"
            )
                
        except Exception as e:
            logger.exception(f"Error exporting category structure: {e}")
            QMessageBox.warning(
                self, "Export Error", 
                f"Error exporting category structure: {str(e)}"
            )

    def _import_category_structure(self):
        """Import a category structure from a JSON file."""
        try:
            from PyQt6.QtWidgets import QFileDialog, QMessageBox
            import json
            
            # Ask for file location
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Import Category Structure", "", "JSON Files (*.json)"
            )
            
            if not file_path:
                return
                
            # Confirm import
            reply = QMessageBox.question(
                self, "Confirm Import",
                "Importing categories may create duplicates if categories with the same names already exist. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
                
            # Read the file
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            # Validate structure
            if 'categories' not in data or not isinstance(data['categories'], list):
                QMessageBox.warning(
                    self, "Invalid Format", 
                    "The selected file does not contain a valid category structure."
                )
                return
                
            # Create a mapping from old IDs to new IDs
            id_mapping = {}
            
            # First pass: Create all categories without parent relationships
            for cat_data in data['categories']:
                new_category = Category(name=cat_data['name'])
                if 'description' in cat_data:
                    new_category.description = cat_data['description']
                    
                self.db_session.add(new_category)
                self.db_session.flush()  # Get the new ID
                
                # Map old ID to new ID
                id_mapping[cat_data['id']] = new_category.id
                
            # Second pass: Set parent relationships
            for cat_data in data['categories']:
                if cat_data['parent_id'] is not None:
                    # Find the category we just created
                    new_id = id_mapping[cat_data['id']]
                    category = self.db_session.query(Category).get(new_id)
                    
                    # Set its parent ID using the mapping
                    if cat_data['parent_id'] in id_mapping:
                        category.parent_id = id_mapping[cat_data['parent_id']]
                        
            # Commit the changes
            self.db_session.commit()
            
            # Refresh knowledge tree
            self._load_knowledge_tree()
            
            QMessageBox.information(
                self, "Import Successful", 
                f"Imported {len(data['categories'])} categories."
            )
                
        except Exception as e:
            logger.exception(f"Error importing category structure: {e}")
            QMessageBox.warning(
                self, "Import Error", 
                f"Error importing category structure: {str(e)}"
            )
            # Rollback in case of error
            self.db_session.rollback()

    def _show_category_statistics(self, category_id):
        """Show statistics for the selected category."""
        try:
            # Get category name
            category_name = "All Categories"
            if category_id is not None:
                category = self.db_session.query(Category).get(category_id)
                if category:
                    category_name = category.name
            
            # Base query for documents
            query = self.db_session.query(Document)
            
            # Apply category filter if specified
            if category_id is not None:
                # Get all subcategory IDs for this category
                category_ids = [category_id]
                self._get_subcategory_ids(category_id, category_ids)
                
                # Filter on this category and all subcategories
                query = query.filter(Document.category_id.in_(category_ids))
            
            # Count total documents
            total_docs = query.count()
            
            # Count new documents (never read)
            new_docs = query.filter(Document.next_reading_date == None).count()
            
            # Count documents by state
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Due today
            due_today = query.filter(
                Document.next_reading_date.between(today, today + timedelta(days=1))
            ).count()
            
            # Overdue
            overdue = query.filter(Document.next_reading_date < today).count()
            
            # Due this week
            due_week = query.filter(
                Document.next_reading_date.between(today, today + timedelta(days=7))
            ).count()
            
            # Count documents by priority
            high_priority = query.filter(Document.priority >= 75).count()
            medium_priority = query.filter(Document.priority.between(50, 74)).count()
            low_priority = query.filter(Document.priority.between(1, 49)).count()
            no_priority = query.filter(Document.priority == 0).count()
            
            # Create statistics message
            stats = f"Statistics for category: {category_name}\n\n"
            stats += f"Total documents: {total_docs}\n"
            stats += f"New documents: {new_docs}\n"
            stats += f"Due today: {due_today}\n"
            stats += f"Overdue: {overdue}\n"
            stats += f"Due this week: {due_week}\n\n"
            
            stats += "Priority distribution:\n"
            if total_docs > 0:
                stats += f"High priority (75-100): {high_priority} ({high_priority/total_docs*100:.1f}%)\n"
                stats += f"Medium priority (50-74): {medium_priority} ({medium_priority/total_docs*100:.1f}%)\n"
                stats += f"Low priority (1-49): {low_priority} ({low_priority/total_docs*100:.1f}%)\n"
                stats += f"No priority (0): {no_priority} ({no_priority/total_docs*100:.1f}%)\n"
            
            # Display statistics
            QMessageBox.information(self, "Category Statistics", stats)
            
        except Exception as e:
            logger.exception(f"Error showing category statistics: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error showing category statistics: {str(e)}"
            )

    def _get_documents_in_category_recursive(self, category_id):
        """Get all documents in a category and its subcategories recursively.
        
        Args:
            category_id: The ID of the parent category
        
        Returns:
            List of document objects in this category and all subcategories
        """
        try:
            # Start with documents directly in this category
            documents = self.db_session.query(Document).filter(Document.category_id == category_id).all()
            
            # Get subcategories
            subcategories = self.db_session.query(Category).filter(Category.parent_id == category_id).all()
            
            # Get documents from each subcategory recursively
            for subcategory in subcategories:
                subcategory_docs = self._get_documents_in_category_recursive(subcategory.id)
                documents.extend(subcategory_docs)
                
            return documents
            
        except Exception as e:
            logger.exception(f"Error getting documents recursively: {e}")
            return []

    def _sort_category_by_fsrs(self, category_id):
        """Sort documents in a category by FSRS score."""
        try:
            # Get all documents in this category and subcategories
            documents = self._get_documents_in_category_recursive(category_id)
            
            if not documents:
                QMessageBox.information(
                    self, "No Documents", 
                    "No documents found in this category to sort."
                )
                return
                
            # Calculate FSRS scores for each document
            scored_documents = []
            for doc in documents:
                score = self._get_fsrs_score(doc)
                scored_documents.append((doc, score))
                
            # Sort by score (higher scores first)
            scored_documents.sort(key=lambda x: x[1], reverse=True)
            
            # Generate report
            if category_id is None:
                category_name = "All Categories"
            else:
                category = self.db_session.query(Category).get(category_id)
                category_name = category.name if category else "Unknown Category"
                
            report = f"FSRS Score Sorting for {category_name}\n\n"
            report += "-" * 60 + "\n"
            report += f"{'Title':<40} {'Score':<10} {'Due Date':<10}\n"
            report += "-" * 60 + "\n"
            
            for doc, score in scored_documents:
                # Format due date
                due_date = "New" if doc.next_reading_date is None else doc.next_reading_date.strftime("%Y-%m-%d")
                # Truncate title if too long
                title = doc.title[:37] + "..." if len(doc.title) > 40 else doc.title.ljust(40)
                report += f"{title} {score:<10.2f} {due_date:<10}\n"
                
            # Show report
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(f"FSRS Sorting - {category_name}")
            msg_box.setText(report)
            msg_box.setDetailedText(f"Sorting used the following parameters:\n"
                                   f"- Minimum interval: {self.fsrs.min_interval}\n"
                                   f"- Maximum interval: {self.fsrs.max_interval}\n"
                                   f"- Interval modifier: {self.fsrs.interval_modifier}\n"
                                   f"- Target retention: {self.fsrs.target_retention}")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            
            # Allow copying of the text
            text_browser = msg_box.findChild(QTextBrowser)
            if text_browser:
                text_browser.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | 
                                                   Qt.TextInteractionFlag.TextSelectableByKeyboard)
            
            # Display the message box with a larger width
            msg_box.setMinimumWidth(600)
            msg_box.exec()
            
        except Exception as e:
            logger.exception(f"Error sorting documents by FSRS: {e}")
            QMessageBox.warning(self, "Error", f"Error sorting documents: {str(e)}")

    def _get_fsrs_score(self, document):
        """Calculate an FSRS-based score for a document to determine review priority.
        
        Returns a score from 0-100, where 100 is highest priority for review.
        """
        try:
            # Base case: if a document has never been reviewed, give it a high priority
            if document.next_reading_date is None or document.reading_count is None or document.reading_count == 0:
                return 90  # High priority for new documents
                
            # If document is overdue, give it very high priority
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if document.next_reading_date < today:
                # The more overdue, the higher the priority
                days_overdue = (today - document.next_reading_date).days
                return min(100, 95 + days_overdue)  # Cap at 100
                
            # For documents due in the future, use a formula that gives higher priority
            # to documents due sooner and those with lower stability (based on reading count)
            days_until_due = (document.next_reading_date - today).days
            
            # Calculate base score from days until due (100 for due today, decreasing for later dates)
            days_score = max(0, 100 - (days_until_due * 5))  # Drops by 5 points per day
            
            # Adjust based on stability (reading count as a proxy)
            stability_factor = max(1, min(5, document.reading_count))  # Range 1-5
            stability_adjustment = (6 - stability_factor) * 5  # Higher adjustment for less stable items
            
            # Final score combines days until due with stability adjustment
            final_score = min(100, days_score + stability_adjustment)
            
            return final_score
            
        except Exception as e:
            logger.exception(f"Error calculating FSRS score: {e}")
            return 50  # Default middle priority on error

    def _toggle_tree_panel(self):
        """Toggle the visibility of the knowledge tree panel."""
        if self.tree_panel.isVisible():
            # Hide tree panel
            self.tree_panel.hide()
            self.main_splitter.setSizes([0, self.main_splitter.width()])
            self.toggle_tree_btn.setToolTip("Show knowledge tree")
            self.toggle_tree_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton))
            self.show_tree_btn.setVisible(True)
            
            # Save state to settings
            if hasattr(self, 'settings_manager'):
                self.settings_manager.set_setting('queue_view', 'tree_panel_visible', False)
        else:
            # Show tree panel
            self.tree_panel.show()
            # Set reasonable split sizes (1:3 ratio)
            width = self.main_splitter.width()
            self.main_splitter.setSizes([int(width * 0.25), int(width * 0.75)])
            self.toggle_tree_btn.setToolTip("Hide knowledge tree")
            self.toggle_tree_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarShadeButton))
            self.show_tree_btn.setVisible(False)
            
            # Save state to settings
            if hasattr(self, 'settings_manager'):
                self.settings_manager.set_setting('queue_view', 'tree_panel_visible', True)

    def _make_tree_dockable(self):
        """Convert the tree panel to a dockable widget."""
        try:
            # Get the main window
            main_window = self.parent()
            while main_window and not isinstance(main_window, QMainWindow):
                main_window = main_window.parent()
                
            if not main_window:
                QMessageBox.warning(self, "Cannot Dock", "Unable to find main window to dock the tree panel.")
                return
                
            # Check if we already have a dock widget
            if hasattr(self, 'tree_dock') and self.tree_dock:
                # If dock exists and is hidden, show it
                if self.tree_dock.isHidden():
                    self.tree_dock.show()
                    # Ensure it has reasonable size
                    self.tree_dock.resize(300, self.tree_dock.height())
                return
                
            # Create a new dock widget
            self.tree_dock = QDockWidget("Knowledge Tree", main_window)
            self.tree_dock.setObjectName("knowledge_tree_dock")
            self.tree_dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | 
                                          Qt.DockWidgetArea.RightDockWidgetArea)
            
            # Set minimum width to prevent it from becoming too small
            self.tree_panel.setMinimumWidth(250)
            
            # Remove tree panel from splitter and add to dock
            self.main_splitter.replaceWidget(0, QWidget())  # Replace with empty widget
            self.tree_dock.setWidget(self.tree_panel)
            
            # Set a reasonable size for the dock
            self.tree_dock.setMinimumWidth(300)
            
            # Add dock widget to main window
            main_window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tree_dock)
            
            # Connect close event
            self.tree_dock.visibilityChanged.connect(self._on_dock_visibility_changed)
            
            # Hide the splitter tree panel since it's now in the dock
            self.tree_panel.setParent(self.tree_dock)
            self.show_tree_btn.setVisible(True)
            
            # Update the show tree button purpose
            self.show_tree_btn.clicked.disconnect()
            self.show_tree_btn.clicked.connect(self._show_tree_dock)
            
            # Save settings
            if hasattr(self, 'settings_manager'):
                self.settings_manager.set_setting('queue_view', 'tree_panel_docked', True)
                
            # Resize the dock to a reasonable width (at least 25% of main window width)
            width = main_window.width()
            self.tree_dock.resize(max(300, int(width * 0.25)), self.tree_dock.height())
            
        except Exception as e:
            logger.exception(f"Error making tree panel dockable: {e}")
            QMessageBox.warning(self, "Error", f"Could not make tree panel dockable: {str(e)}")

    def _show_tree_dock(self):
        """Show the tree dock if it exists."""
        try:
            if hasattr(self, 'tree_dock') and self.tree_dock:
                # Get the main window
                main_window = self.parent()
                while main_window and not isinstance(main_window, QMainWindow):
                    main_window = main_window.parent()
                    
                # Show the dock
                self.tree_dock.show()
                self.tree_dock.raise_()
                
                # Resize to a reasonable width if it appears too small
                if self.tree_dock.width() < 200:
                    width = main_window.width() if main_window else 800
                    self.tree_dock.resize(max(300, int(width * 0.25)), self.tree_dock.height())
                    
                # Update action state in main window if it exists
                if main_window:
                    action = main_window.findChild(QAction, "action_toggle_knowledge_tree")
                    if action and isinstance(action, QAction):
                        action.setChecked(True)
            else:
                # Fallback to showing the regular tree panel
                self._toggle_tree_panel()
        except Exception as e:
            logger.exception(f"Error showing tree dock: {e}")

    def _on_dock_visibility_changed(self, visible):
        """Handle dock widget visibility changes."""
        try:
            self.show_tree_btn.setVisible(not visible)
            
            # Update action state in main window
            main_window = self.parent()
            while main_window and not isinstance(main_window, QMainWindow):
                main_window = main_window.parent()
            
            if main_window:
                action = main_window.findChild(QAction, "action_toggle_knowledge_tree")
                if action and isinstance(action, QAction):
                    action.setChecked(visible)
            
            # Save settings
            if hasattr(self, 'settings_manager'):
                self.settings_manager.set_setting('queue_view', 'tree_dock_visible', visible)
        except Exception as e:
            logger.exception(f"Error handling dock visibility change: {e}")

    def keyPressEvent(self, event):
        """Handle keyboard events for queue navigation and rating."""
        key = event.key()
        
        # Check for digit keys 1-5 for ratings (alternative to shortcuts)
        if Qt.Key.Key_1 <= key <= Qt.Key.Key_5:
            rating = key - Qt.Key.Key_0  # Convert key code to number (1-5)
            self._rate_current_document(rating)
            event.accept()
            return
        
        # Check for N/P keys for navigation (alternative to shortcuts)
        elif key == Qt.Key.Key_N:
            self._on_read_next()
            event.accept()
            return
        elif key == Qt.Key.Key_P:
            self._on_read_prev()
            event.accept()
            return
        
        # Pass event to parent for default handling
        super().keyPressEvent(event)

    def _create_ui(self):
        """Create UI elements."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create main splitter to hold knowledge tree and tabbed queue area
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(2)  # Narrower handle
        self.main_splitter.setChildrenCollapsible(False)  # Allow sections to be collapsed
        
        # Setup the knowledge tree panel (left side)
        self.tree_panel = QWidget()
        tree_layout = QVBoxLayout(self.tree_panel)
        tree_layout.setContentsMargins(2, 2, 2, 2)
        
        # Add title and buttons for knowledge tree
        tree_header_layout = QHBoxLayout()
        
        tree_title = QLabel("Knowledge Tree")
        tree_title.setStyleSheet("font-weight: bold;")
        tree_header_layout.addWidget(tree_title, 1)  # Give title more space
        
        # Create button toolbar with tooltips and icons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(2)  # Tighter spacing for buttons
        
        # Add folder button
        self.add_folder_btn = QPushButton()
        self.add_folder_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        self.add_folder_btn.setToolTip("Add new category")
        self.add_folder_btn.setMaximumWidth(30)
        self.add_folder_btn.clicked.connect(self.add_folder_to_tree)
        button_layout.addWidget(self.add_folder_btn)
        
        # Delete folder button
        self.del_folder_btn = QPushButton()
        self.del_folder_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        self.del_folder_btn.setToolTip("Delete selected category")
        self.del_folder_btn.setMaximumWidth(30)
        self.del_folder_btn.clicked.connect(self.delete_folder_from_tree)
        button_layout.addWidget(self.del_folder_btn)
        
        # Expand/Collapse buttons
        self.expand_all_btn = QPushButton()
        self.expand_all_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.expand_all_btn.setToolTip("Expand all categories")
        self.expand_all_btn.setMaximumWidth(30)
        self.expand_all_btn.clicked.connect(self._expand_all_categories)
        button_layout.addWidget(self.expand_all_btn)
        
        self.collapse_all_btn = QPushButton()
        self.collapse_all_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.collapse_all_btn.setToolTip("Collapse all categories")
        self.collapse_all_btn.setMaximumWidth(30)
        self.collapse_all_btn.clicked.connect(self._collapse_all_categories)
        button_layout.addWidget(self.collapse_all_btn)
        
        # Hide/Show tree panel button
        self.toggle_tree_btn = QPushButton()
        self.toggle_tree_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton))
        self.toggle_tree_btn.setToolTip("Hide knowledge tree")
        self.toggle_tree_btn.setMaximumWidth(30)
        self.toggle_tree_btn.clicked.connect(self._toggle_tree_panel)
        button_layout.addWidget(self.toggle_tree_btn)
        
        # Add buttons to header layout
        tree_header_layout.addLayout(button_layout)
        
        # Theme selector
        self.theme_combo = QComboBox()
        self.theme_combo.setMaximumWidth(100)
        self.theme_combo.addItems(["Default", "Dark", "Light", "SuperMemo", "Custom"])
        self.theme_combo.setToolTip("Select theme for UI")
        self.theme_combo.currentIndexChanged.connect(self._apply_theme)
        tree_header_layout.addWidget(self.theme_combo)
        
        tree_layout.addLayout(tree_header_layout)
        
        # Add search box for the tree
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)
        
        self.tree_search_box = QComboBox()
        self.tree_search_box.setEditable(True)
        self.tree_search_box.setInsertPolicy(QComboBox.InsertPolicy.InsertAtTop)
        self.tree_search_box.setMaxCount(10)  # Remember last 10 searches
        self.tree_search_box.lineEdit().returnPressed.connect(self._on_tree_search)
        search_layout.addWidget(self.tree_search_box, 1)
        
        search_btn = QPushButton("Find")
        search_btn.clicked.connect(self._on_tree_search)
        search_layout.addWidget(search_btn)
        
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_tree_search)
        search_layout.addWidget(clear_btn)
        
        tree_layout.addLayout(search_layout)
        
        # Create knowledge tree widget
        self.knowledge_tree = QTreeWidget()
        self.knowledge_tree.setObjectName("knowledge_tree")
        self.knowledge_tree.setColumnCount(2)
        self.knowledge_tree.setHeaderLabels(["Category", "Documents"])
        self.knowledge_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.knowledge_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.knowledge_tree.setSelectionBehavior(QTreeWidget.SelectionBehavior.SelectRows)
        self.knowledge_tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.knowledge_tree.itemClicked.connect(self._on_knowledge_tree_item_clicked)
        self.knowledge_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.knowledge_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        
        # Set reasonable minimum size for tree
        self.knowledge_tree.setMinimumWidth(180)
        
        # Set size policy to allow expansion
        self.knowledge_tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        tree_layout.addWidget(self.knowledge_tree)
        
        # Filter options for the tree view
        tree_filter_layout = QHBoxLayout()
        
        self.show_empty_check = QCheckBox("Show Empty Categories")
        self.show_empty_check.setChecked(True)
        self.show_empty_check.stateChanged.connect(self._on_tree_filter_changed)
        tree_filter_layout.addWidget(self.show_empty_check)
        
        self.sort_alpha_check = QCheckBox("Sort Alphabetically")
        self.sort_alpha_check.setChecked(True)
        self.sort_alpha_check.stateChanged.connect(self._on_tree_filter_changed)
        tree_filter_layout.addWidget(self.sort_alpha_check)
        
        tree_layout.addLayout(tree_filter_layout)
        
        # Create floating option button for the tree
        dock_tree_btn = QPushButton("Dock")
        dock_tree_btn.setToolTip("Make tree panel dockable")
        dock_tree_btn.clicked.connect(self._make_tree_dockable)
        tree_filter_layout.addWidget(dock_tree_btn)

        # Setup the queue panel (right side)
        self.queue_panel = QWidget()
        self.queue_panel.setObjectName("queue_panel")
        queue_layout = QVBoxLayout(self.queue_panel)
        queue_layout.setContentsMargins(2, 2, 2, 2)
        
        # Create show tree button for when tree is hidden
        self.show_tree_btn = QPushButton()
        self.show_tree_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
        self.show_tree_btn.setToolTip("Show knowledge tree")
        self.show_tree_btn.clicked.connect(self._toggle_tree_panel)
        self.show_tree_btn.setVisible(False)  # Initially hidden
        
        # Add title and buttons for queue
        queue_header_layout = QHBoxLayout()
        
        # Add show tree button at the start of the queue header
        queue_header_layout.addWidget(self.show_tree_btn)
        
        queue_title = QLabel("Reading Queue")
        queue_title.setStyleSheet("font-weight: bold;")
        queue_header_layout.addWidget(queue_title)
        
        # Filter controls for queue
        queue_filter_layout = QHBoxLayout()
        
        category_label = QLabel("Category:")
        queue_filter_layout.addWidget(category_label)
        
        self.category_combo = QComboBox()
        self.category_combo.setObjectName("category_combo")
        self.category_combo.currentIndexChanged.connect(self._on_filter_changed)
        queue_filter_layout.addWidget(self.category_combo)
        
        days_label = QLabel("Days ahead:")
        queue_filter_layout.addWidget(days_label)
        
        self.days_ahead_spin = QSpinBox()
        self.days_ahead_spin.setObjectName("days_ahead_spin")
        self.days_ahead_spin.setRange(1, 30)
        self.days_ahead_spin.setValue(7)
        self.days_ahead_spin.valueChanged.connect(self._on_filter_changed)
        queue_filter_layout.addWidget(self.days_ahead_spin)
        
        self.include_new_check = QCheckBox("Include new")
        self.include_new_check.setObjectName("include_new_check")
        self.include_new_check.setChecked(True)
        self.include_new_check.stateChanged.connect(self._on_filter_changed)
        queue_filter_layout.addWidget(self.include_new_check)
        
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._on_refresh)
        queue_filter_layout.addWidget(self.refresh_button)
        
        # Create tabbed queue widget
        self.queue_tabs = QTabWidget()
        self.queue_tabs.setObjectName("queue_tabs")
        self.queue_tabs.currentChanged.connect(self._on_tab_changed)
        
        # Create main tabs: queue list and calendar view
        self._create_queue_tab()
        self._create_calendar_tab()
        
        # Add statistics area
        stats_group = QGroupBox("Queue Statistics")
        stats_layout = QHBoxLayout(stats_group)
        
        # Create stat labels
        self.total_label = QLabel("0")
        self.due_today_label = QLabel("0")
        self.due_week_label = QLabel("0")
        self.overdue_label = QLabel("0")
        self.new_label = QLabel("0")
        
        # Create form layout for stats
        stats_form = QFormLayout()
        stats_form.addRow("Total:", self.total_label)
        stats_form.addRow("Due today:", self.due_today_label)
        stats_form.addRow("Due this week:", self.due_week_label)
        stats_form.addRow("Overdue:", self.overdue_label)
        stats_form.addRow("New:", self.new_label)
        
        stats_layout.addLayout(stats_form)
        
        # Navigation controls
        nav_layout = QHBoxLayout()
        
        # Create navigation buttons
        self.read_next_button = QPushButton("Next Document")
        self.read_next_button.clicked.connect(self._on_read_next)
        nav_layout.addWidget(self.read_next_button)
        
        self.prev_button = QPushButton("Previous")
        self.prev_button.clicked.connect(self._on_read_prev)
        nav_layout.addWidget(self.prev_button)
        
        # Add all layouts to the queue panel
        queue_layout.addLayout(queue_header_layout)
        queue_layout.addLayout(queue_filter_layout)
        queue_layout.addWidget(self.queue_tabs, stretch=1)
        queue_layout.addWidget(stats_group)
        queue_layout.addLayout(nav_layout)
        
        # Set reasonable minimum size for queue panel
        self.queue_panel.setMinimumWidth(400)
        
        # Set size policy to allow expansion
        self.queue_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Add both panels to the main splitter
        self.main_splitter.addWidget(self.tree_panel)
        self.main_splitter.addWidget(self.queue_panel)
        
        # Set initial sizes (1:2 ratio by default)
        self.main_splitter.setSizes([300, 600])
        
        # Connect splitter moved signal to save state
        self.main_splitter.splitterMoved.connect(self._on_splitter_moved)
        
        # Add the splitter to the main layout
        main_layout.addWidget(self.main_splitter)
        
        # Populate initially
        self._populate_categories()

    def _create_queue_tab(self):
        """Create the queue tab with document list."""
        queue_tab = QWidget()
        queue_tab.setObjectName("queue_tab")
        queue_layout = QVBoxLayout(queue_tab)
        
        # Add filter controls
        filter_layout = QHBoxLayout()
        
        # Search box
        search_label = QLabel("Search:")
        filter_layout.addWidget(search_label)
        
        self.queue_search_box = QLineEdit()
        self.queue_search_box.setPlaceholderText("Search titles...")
        self.queue_search_box.returnPressed.connect(self._on_queue_search)
        filter_layout.addWidget(self.queue_search_box)
        
        # Sort options
        sort_label = QLabel("Sort by:")
        filter_layout.addWidget(sort_label)
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Priority", "Due Date", "Category", "Reading Count", "Title"])
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        filter_layout.addWidget(self.sort_combo)
        
        # Sort direction
        self.sort_asc_button = QPushButton()
        self.sort_asc_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        self.sort_asc_button.setToolTip("Sort Ascending")
        self.sort_asc_button.setCheckable(True)
        self.sort_asc_button.setChecked(False)
        self.sort_asc_button.clicked.connect(self._on_sort_changed)
        filter_layout.addWidget(self.sort_asc_button)
        
        # Favorite filter
        self.show_favorites_only = QCheckBox("Favorites Only")
        self.show_favorites_only.setChecked(False)
        self.show_favorites_only.stateChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.show_favorites_only)
        
        # Clear filters button
        clear_filters_btn = QPushButton("Clear Filters")
        clear_filters_btn.clicked.connect(self._clear_queue_filters)
        filter_layout.addWidget(clear_filters_btn)
        
        queue_layout.addLayout(filter_layout)
        
        # Create queue table
        self.queue_table = QTableWidget()
        self.queue_table.setObjectName("queue_table")
        self.queue_table.setColumnCount(5)
        self.queue_table.setHorizontalHeaderLabels(["Title", "Priority", "Due Date", "Category", "Reading Count"])
        self.queue_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.queue_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.queue_table.doubleClicked.connect(self._on_document_selected)
        self.queue_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_table.customContextMenuRequested.connect(self._on_queue_context_menu)
        
        queue_layout.addWidget(self.queue_table)
        
        # Add to tabs
        self.queue_tabs.addTab(queue_tab, "Queue List")

    def _create_calendar_tab(self):
        """Create the calendar view tab."""
        calendar_tab = QWidget()
        calendar_tab.setObjectName("calendar_tab")
        calendar_layout = QVBoxLayout(calendar_tab)
        
        # Placeholder for calendar view implementation
        calendar_label = QLabel("Calendar view under development")
        calendar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        calendar_layout.addWidget(calendar_label)
        
        # Add to tabs
        self.queue_tabs.addTab(calendar_tab, "Calendar View")

    def _populate_categories(self):
        """Populate the categories dropdown."""
        try:
            if not hasattr(self, 'category_combo'):
                return
            
            # Save current selection if any
            current_id = None
            if self.category_combo.currentIndex() >= 0:
                current_id = self.category_combo.currentData(Qt.ItemDataRole.UserRole)
            
            # Clear and populate
            self.category_combo.clear()
            
            # Add "All Categories" option
            self.category_combo.addItem("All Categories", None)
            
            # Add all categories
            populate_category_combo(self.category_combo, self.db_session)
            
            # Restore selection if possible
            if current_id is not None:
                # Find the index with this category ID
                for i in range(self.category_combo.count()):
                    if self.category_combo.itemData(i, Qt.ItemDataRole.UserRole) == current_id:
                        self.category_combo.setCurrentIndex(i)
                        break
        except Exception as e:
            logger.exception(f"Error populating categories: {e}")

    def _on_read_next(self):
        """Read the next document in the queue."""
        try:
            # Get current selected row
            current_row = self.queue_table.currentRow()
            
            # If no selection, start with first row
            if current_row < 0 and self.queue_table.rowCount() > 0:
                self.queue_table.selectRow(0)
                current_row = 0
            
            # If there's a next row, select it
            if 0 <= current_row < self.queue_table.rowCount() - 1:
                self.queue_table.selectRow(current_row + 1)
                # Get document ID from selected row
                document_id = self.queue_table.item(current_row + 1, 0).data(Qt.ItemDataRole.UserRole)
                # Emit signal to open document
                self.documentSelected.emit(document_id)
            else:
                # No next document
                QMessageBox.information(self, "End of Queue", "You've reached the end of the queue.")
        except Exception as e:
            logger.exception(f"Error reading next document: {e}")

    def _on_read_prev(self):
        """Read the previous document in the queue."""
        try:
            # Get current selected row
            current_row = self.queue_table.currentRow()
            
            # If there's a previous row, select it
            if current_row > 0:
                self.queue_table.selectRow(current_row - 1)
                # Get document ID from selected row
                document_id = self.queue_table.item(current_row - 1, 0).data(Qt.ItemDataRole.UserRole)
                # Emit signal to open document
                self.documentSelected.emit(document_id)
            else:
                # No previous document
                QMessageBox.information(self, "Start of Queue", "You're at the start of the queue.")
        except Exception as e:
            logger.exception(f"Error reading previous document: {e}")

    def _on_filter_changed(self):
        """Handle changes to any filter control."""
        # Reload queue data with new filter
        self._load_queue_data()

    def _on_refresh(self):
        """Refresh queue data."""
        self._load_queue_data()

    def _on_splitter_moved(self):
        """Handle splitter movement to save state."""
        if hasattr(self, 'settings_manager'):
            # Save the splitter sizes to settings
            sizes = self.main_splitter.sizes()
            self.settings_manager.set_setting('queue_view', 'splitter_sizes', sizes)

    def _on_knowledge_tree_item_clicked(self, item):
        """Handle clicking on a knowledge tree item."""
        try:
            # Check if item is valid (not deleted)
            if not item or not hasattr(item, 'data'):
                logger.warning("Ignoring click on deleted tree item")
                return
            
            # Get category ID from item
            category_id = item.data(0, Qt.ItemDataRole.UserRole)
            
            # Select this category in the filter combo box
            for i in range(self.category_combo.count()):
                combo_category_id = self.category_combo.itemData(i, Qt.ItemDataRole.UserRole)
                if combo_category_id == category_id:
                    self.category_combo.setCurrentIndex(i)
                    break
        except RuntimeError as e:
            logger.error(f"RuntimeError in tree item click handler: {e}")
        except Exception as e:
            logger.exception(f"Error handling tree item click: {e}")

    def _on_tree_context_menu(self, position):
        """Show context menu for knowledge tree."""
        try:
            # Get clicked item
            item = self.knowledge_tree.itemAt(position)
            
            # Check if item is valid (not deleted)
            if not item or not hasattr(item, 'data'):
                logger.warning("Ignoring context menu on deleted tree item")
                return
            
            # Get category ID from item
            category_id = item.data(0, Qt.ItemDataRole.UserRole)
            
            # Create context menu
            context_menu = QMenu(self)
            
            # Add actions
            if category_id is not None:
                # Regular category actions
                rename_action = QAction("Rename Category", self)
                rename_action.triggered.connect(lambda: self._rename_category_tree_item(item))
                context_menu.addAction(rename_action)
                
                # Add subcategory action
                add_subcategory_action = QAction("Add Subcategory", self)
                add_subcategory_action.triggered.connect(lambda: self._add_subcategory(category_id))
                context_menu.addAction(add_subcategory_action)
                
                # Show stats action
                stats_action = QAction("Show Statistics", self)
                stats_action.triggered.connect(lambda: self._show_category_statistics(category_id))
                context_menu.addAction(stats_action)
                
                # Sort by FSRS action
                sort_action = QAction("Sort by FSRS Score", self)
                sort_action.triggered.connect(lambda: self._sort_category_by_fsrs(category_id))
                context_menu.addAction(sort_action)
            else:
                # Special actions for "All Categories"
                stats_action = QAction("Show Statistics", self)
                stats_action.triggered.connect(lambda: self._show_category_statistics(None))
                context_menu.addAction(stats_action)
            
            # Add common actions
            context_menu.addSeparator()
            
            # Export/Import actions
            export_action = QAction("Export Categories", self)
            export_action.triggered.connect(self._export_category_structure)
            context_menu.addAction(export_action)
            
            import_action = QAction("Import Categories", self)
            import_action.triggered.connect(self._import_category_structure)
            context_menu.addAction(import_action)
            
            # Show the menu
            context_menu.exec(self.knowledge_tree.mapToGlobal(position))
        except RuntimeError as e:
            logger.error(f"RuntimeError in context menu handler: {e}")
        except Exception as e:
            logger.exception(f"Error showing context menu: {e}")

    def add_folder_to_tree(self):
        """Add a new top-level category."""
        try:
            # Ask for category name
            category_name, ok = QInputDialog.getText(
                self, "New Category", "Enter category name:"
            )
            
            if not ok or not category_name.strip():
                return
                
            # Check for duplicate names at the top level
            existing = self.db_session.query(Category).filter(
                Category.name == category_name,
                Category.parent_id == None
            ).first()
            
            if existing:
                QMessageBox.warning(
                    self, "Duplicate Name", 
                    f"A category named '{category_name}' already exists at the top level."
                )
                return
                
            # Create new category in database
            new_category = Category(name=category_name)
            self.db_session.add(new_category)
            self.db_session.commit()
            
            # Refresh knowledge tree
            self._load_knowledge_tree()
            
            # Select the new category
            self._select_category_by_name(category_name)
            
            # Show success message
            QMessageBox.information(
                self, "Success", 
                f"Category '{category_name}' created successfully."
            )
        except Exception as e:
            logger.exception(f"Error creating category: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error creating category: {str(e)}"
            )
            # Rollback in case of error
            self.db_session.rollback()

    def delete_folder_from_tree(self):
        """Delete the selected category from the tree."""
        try:
            # Get selected item
            item = self.knowledge_tree.currentItem()
            if not item:
                QMessageBox.warning(self, "No Selection", "Please select a category to delete.")
                return
                
            # Get category ID
            category_id = item.data(0, Qt.ItemDataRole.UserRole)
            if category_id is None:
                QMessageBox.warning(self, "Cannot Delete", "The 'All Categories' item cannot be deleted.")
                return
                
            # Get the category from the database
            category = self.db_session.query(Category).get(category_id)
            if not category:
                QMessageBox.warning(self, "Error", "Category not found in database.")
                return
                
            # Ask for confirmation
            reply = QMessageBox.question(
                self, "Confirm Deletion",
                f"Are you sure you want to delete the category '{category.name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
                
            # Check for subcategories
            subcategories = self.db_session.query(Category).filter(Category.parent_id == category_id).count()
            if subcategories > 0:
                QMessageBox.warning(
                    self, "Cannot Delete", 
                    "This category has subcategories. Please delete or move the subcategories first."
                )
                return
                
            # Check for documents
            documents = self.db_session.query(Document).filter(Document.category_id == category_id).count()
            if documents > 0:
                # Ask what to do with documents
                reply = QMessageBox.question(
                    self, "Documents Found",
                    f"This category contains {documents} documents. What would you like to do?",
                    QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Save,
                    QMessageBox.StandardButton.Cancel
                )
                
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                elif reply == QMessageBox.StandardButton.Save:
                    # Move documents to uncategorized
                    for doc in self.db_session.query(Document).filter(Document.category_id == category_id).all():
                        doc.category_id = None
                        self.db_session.add(doc)
                elif reply == QMessageBox.StandardButton.Discard:
                    # Ask for additional confirmation before deleting documents
                    confirm_delete = QMessageBox.warning(
                        self, "Confirm Document Deletion",
                        f"Are you sure you want to DELETE {documents} documents? This cannot be undone.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )
                    
                    if confirm_delete != QMessageBox.StandardButton.Yes:
                        return
                        
                    # Delete all documents in this category
                    self.db_session.query(Document).filter(Document.category_id == category_id).delete()
            
            # Store the category name for the success message
            category_name = category.name
            
            # Delete the category
            self.db_session.delete(category)
            self.db_session.commit()
            
            # Refresh knowledge tree
            self._load_knowledge_tree()
            
            # Refresh categories dropdown
            self._populate_categories()
            
            # Show success message
            QMessageBox.information(self, "Success", f"Category '{category_name}' deleted successfully.")
                
        except Exception as e:
            logger.exception(f"Error deleting category: {e}")
            try:
                QMessageBox.warning(
                    self, "Error", 
                    f"Error deleting category: {str(e)}"
                )
            except:
                logger.critical("Could not show error message dialog")
            # Rollback in case of error
            self.db_session.rollback()

    def _on_document_selected(self, index):
        """Handle document selection from the queue table."""
        try:
            # Get document ID from selected row
            row = index.row()
            document_id = self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            
            # Emit signal to open document
            self.documentSelected.emit(document_id)
        except Exception as e:
            logger.exception(f"Error selecting document: {e}")

    def _on_queue_context_menu(self, position):
        """Show context menu for queue table."""
        try:
            # Get clicked row
            row = self.queue_table.rowAt(position.y())
            if row < 0:
                return
            
            # Get document ID
            document_id = self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            
            # Get the document to check favorite status
            document = self.db_session.query(Document).get(document_id)
            is_favorite = hasattr(document, 'is_favorite') and document.is_favorite
            
            # Create context menu
            context_menu = QMenu(self)
            
            # Add actions
            open_action = QAction("Open Document", self)
            open_action.triggered.connect(lambda: self.documentSelected.emit(document_id))
            context_menu.addAction(open_action)
            
            # Favorite/unfavorite action
            if is_favorite:
                favorite_action = QAction("Remove from Favorites", self)
                favorite_action.triggered.connect(lambda: self._toggle_favorite(document_id, False))
            else:
                favorite_action = QAction("Add to Favorites", self)
                favorite_action.triggered.connect(lambda: self._toggle_favorite(document_id, True))
            context_menu.addAction(favorite_action)
            
            # Add rating actions
            context_menu.addSeparator()
            context_menu.addSection("Rate Document")
            
            for rating in range(1, 6):
                rate_action = QAction(f"Rate {rating}/5", self)
                rate_action.triggered.connect(lambda r=rating: self._rate_document(document_id, r))
                context_menu.addAction(rate_action)
            
            # Add priority actions
            context_menu.addSeparator()
            context_menu.addSection("Set Priority")
            
            priorities = {
                "Very High (100)": 100,
                "High (75)": 75,
                "Medium (50)": 50,
                "Low (25)": 25,
                "Very Low (10)": 10
            }
            
            for name, value in priorities.items():
                priority_action = QAction(name, self)
                priority_action.triggered.connect(lambda v=value: self._set_document_priority(document_id, v))
                context_menu.addAction(priority_action)
            
            # Add reschedule actions
            context_menu.addSeparator()
            context_menu.addSection("Reschedule")
            
            reschedule_options = {
                "Today": 0,
                "Tomorrow": 1,
                "In 3 days": 3,
                "In 1 week": 7,
                "In 2 weeks": 14,
                "In 1 month": 30,
                "In 3 months": 90
            }
            
            for name, days in reschedule_options.items():
                reschedule_action = QAction(name, self)
                reschedule_action.triggered.connect(lambda d=days: self._reschedule_document(document_id, d))
                context_menu.addAction(reschedule_action)
            
            # Show the menu
            context_menu.exec(self.queue_table.mapToGlobal(position))
        except Exception as e:
            logger.exception(f"Error showing queue context menu: {e}")
        
    def _toggle_favorite(self, document_id, is_favorite):
        """Toggle the favorite status of a document."""
        try:
            # Check if the document exists
            document = self.db_session.query(Document).get(document_id)
            if not document:
                QMessageBox.warning(self, "Error", "Document not found.")
                return
                
            # Check if the column exists in the schema
            if not hasattr(document, 'is_favorite'):
                # Need to add the column to the schema
                from sqlalchemy import Column, Boolean
                from sqlalchemy.ext.declarative import declarative_base
                
                # Add the column to the Document model
                Document.is_favorite = Column(Boolean, default=False)
                
                # Check if the column already exists in the database
                try:
                    # First check if the column already exists
                    from sqlalchemy import text
                    result = self.db_session.execute(text("PRAGMA table_info(documents)"))
                    columns = result.fetchall()
                    column_names = [column[1] for column in columns]
                    
                    if 'is_favorite' not in column_names:
                        # Column doesn't exist - add it
                        self.db_session.execute(text("ALTER TABLE documents ADD COLUMN is_favorite BOOLEAN DEFAULT 0"))
                        self.db_session.commit()
                except Exception as e:
                    logger.error(f"Error checking/adding is_favorite column: {e}")
                    self.db_session.rollback()
                    raise
                
            # Update the favorite status
            document.is_favorite = is_favorite
            self.db_session.commit()
            
            # Refresh the queue to show the updated status
            self._load_queue_data()
            
            # Show confirmation
            status = "added to" if is_favorite else "removed from"
            QMessageBox.information(
                self, "Favorite Updated", 
                f"Document '{document.title}' {status} favorites."
            )
                
        except Exception as e:
            logger.exception(f"Error toggling favorite status: {e}")
            QMessageBox.warning(self, "Error", f"Error updating favorite status: {str(e)}")
            # Rollback in case of error
            self.db_session.rollback()
        
    def _reschedule_document(self, document_id, days_ahead):
        """Reschedule a document for a specific number of days from today."""
        try:
            # Check if the document exists
            document = self.db_session.query(Document).get(document_id)
            if not document:
                QMessageBox.warning(self, "Error", "Document not found.")
                return
                
            # Calculate new date
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            new_date = today + timedelta(days=days_ahead)
            
            # Update the document
            document.next_reading_date = new_date
            self.db_session.commit()
            
            # Refresh the queue
            self._load_queue_data()
            
            # Show confirmation
            when = "today" if days_ahead == 0 else f"for {new_date.strftime('%Y-%m-%d')}"
            QMessageBox.information(
                self, "Document Rescheduled", 
                f"Document '{document.title}' rescheduled {when}."
            )
                
        except Exception as e:
            logger.exception(f"Error rescheduling document: {e}")
            QMessageBox.warning(self, "Error", f"Error rescheduling document: {str(e)}")
            # Rollback in case of error
            self.db_session.rollback()

    def _on_tab_changed(self, index):
        """Handle changing tabs."""
        # Save active tab in settings
        if hasattr(self, 'settings_manager'):
            self.settings_manager.set_setting('queue_view', 'active_tab', index)

    def saveState(self):
        """Save the widget state for session management."""
        if hasattr(self, 'settings_manager'):
            # Save splitter sizes
            if hasattr(self, 'main_splitter'):
                self.settings_manager.set_setting('queue_view', 'splitter_sizes', self.main_splitter.sizes())
            
            # Save active tab
            if hasattr(self, 'queue_tabs'):
                self.settings_manager.set_setting('queue_view', 'active_tab', self.queue_tabs.currentIndex())
            
            # Save tree panel visibility
            if hasattr(self, 'tree_panel'):
                self.settings_manager.set_setting('queue_view', 'tree_panel_visible', self.tree_panel.isVisible())

    def restoreState(self):
        """Restore the widget state from session management."""
        if hasattr(self, 'settings_manager'):
            # Restore splitter sizes
            if hasattr(self, 'main_splitter'):
                sizes = self.settings_manager.get_setting('queue_view', 'splitter_sizes', None)
                if sizes:
                    self.main_splitter.setSizes(sizes)
            
            # Restore active tab
            if hasattr(self, 'queue_tabs'):
                active_tab = self.settings_manager.get_setting('queue_view', 'active_tab', 0)
                self.queue_tabs.setCurrentIndex(active_tab)
            
            # Restore tree panel visibility
            if hasattr(self, 'tree_panel'):
                visible = self.settings_manager.get_setting('queue_view', 'tree_panel_visible', True)
                if not visible:
                    self._toggle_tree_panel()

    def _rate_current_document(self, rating):
        """Rate the currently selected document."""
        # Get current selected row
        current_row = self.queue_table.currentRow()
        if current_row >= 0:
            # Get document ID from selected row
            document_id = self.queue_table.item(current_row, 0).data(Qt.ItemDataRole.UserRole)
            # Rate the document
            self._rate_document(document_id, rating)

    def _rate_document(self, document_id, rating):
        """Rate a document and update its next reading date."""
        try:
            # Get the document
            document = self.db_session.query(Document).get(document_id)
            if not document:
                QMessageBox.warning(self, "Error", "Document not found.")
                return
            
            # Create or update the incremental reading record
            ir_record = self.db_session.query(IncrementalReading).filter_by(document_id=document_id).first()
            if not ir_record:
                ir_record = IncrementalReading(document_id=document_id)
                self.db_session.add(ir_record)
            
            # Update last rating
            ir_record.last_rating = rating
            
            # Increment reading count
            if document.reading_count is None:
                document.reading_count = 1
            else:
                document.reading_count += 1
            
            # Calculate next reading date using FSRS
            next_date = self.fsrs.calculate_next_date(document, rating)
            document.next_reading_date = next_date
            
            # Update document
            self.db_session.add(document)
            self.db_session.commit()
            
            # Refresh queue
            self._load_queue_data()
            
            # Show confirmation
            QMessageBox.information(
                self, "Document Rated", 
                f"Document rated {rating}/5. Next review scheduled for {next_date.strftime('%Y-%m-%d')}."
            )
            
        except Exception as e:
            logger.exception(f"Error rating document: {e}")
            QMessageBox.warning(self, "Error", f"Error rating document: {str(e)}")
            # Rollback in case of error
            self.db_session.rollback()

    def _set_document_priority(self, document_id, priority):
        """Set the priority of a document."""
        try:
            # Get the document
            document = self.db_session.query(Document).get(document_id)
            if not document:
                QMessageBox.warning(self, "Error", "Document not found.")
                return
            
            # Update priority
            document.priority = priority
            self.db_session.add(document)
            self.db_session.commit()
            
            # Refresh queue
            self._load_queue_data()
            
        except Exception as e:
            logger.exception(f"Error setting document priority: {e}")
            QMessageBox.warning(self, "Error", f"Error setting document priority: {str(e)}")
            # Rollback in case of error
            self.db_session.rollback()

    def _setup_queue_drag_drop(self):
        """Set up drag and drop for the queue table."""
        try:
            # Set drag enabled for queue table
            self.queue_table.setDragEnabled(True)
            self.queue_table.setAcceptDrops(True)
            self.queue_table.setDropIndicatorShown(True)
            self.queue_table.setDragDropMode(QTableWidget.DragDropMode.DragDrop)
            
            # Accept drops for the knowledge tree
            self.knowledge_tree.setAcceptDrops(True)
            self.knowledge_tree.setDropIndicatorShown(True)
            self.knowledge_tree.setDragDropMode(QTreeWidget.DragDropMode.DropOnly)
            
        except Exception as e:
            logger.exception(f"Error setting up drag and drop: {e}")

    def _load_queue_data(self):
        """Load documents into the queue table based on current filter settings."""
        try:
            if not hasattr(self, 'queue_table'):
                logger.warning("Queue table not available")
                return
            
            # Clear existing items
            self.queue_table.setRowCount(0)
            
            # Get filter settings
            days_ahead = self.days_ahead_spin.value()
            include_new = self.include_new_check.isChecked()
            category_id = self.category_combo.currentData(Qt.ItemDataRole.UserRole)
            show_favorites_only = hasattr(self, 'show_favorites_only') and self.show_favorites_only.isChecked()
            
            # Get sort settings
            if hasattr(self, 'sort_combo'):
                sort_column = self.sort_combo.currentIndex()
                sort_ascending = self.sort_asc_button.isChecked()
            else:
                # Default to priority, descending
                sort_column = 0
                sort_ascending = False
            
            # Base query for documents
            query = self.db_session.query(Document)
            
            # Apply category filter if specified
            if category_id is not None:
                # Get all subcategory IDs for this category
                category_ids = [category_id]
                self._get_subcategory_ids(category_id, category_ids)
                
                # Filter on this category and all subcategories
                query = query.filter(Document.category_id.in_(category_ids))
            
            # Apply favorites filter if enabled
            if show_favorites_only:
                query = query.filter(Document.is_favorite == True)
            
            # Calculate date range for filter
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = today + timedelta(days=days_ahead)
            
            # Apply date filters
            if include_new:
                # Include both new documents and those due within the date range
                query = query.filter(
                    (Document.next_reading_date == None) |
                    (Document.next_reading_date <= end_date)
                )
            else:
                # Only include documents due within the date range
                query = query.filter(Document.next_reading_date <= end_date)
            
            # Apply sorting
            if sort_column == 0:  # Priority
                query = query.order_by(Document.priority.asc() if sort_ascending else Document.priority.desc())
            elif sort_column == 1:  # Due Date
                query = query.order_by(Document.next_reading_date.asc() if sort_ascending else Document.next_reading_date.desc())
            elif sort_column == 2:  # Category - need to join with Category
                if sort_ascending:
                    query = query.join(Category, Document.category_id == Category.id, isouter=True).order_by(Category.name.asc())
                else:
                    query = query.join(Category, Document.category_id == Category.id, isouter=True).order_by(Category.name.desc())
            elif sort_column == 3:  # Reading Count
                query = query.order_by(Document.reading_count.asc() if sort_ascending else Document.reading_count.desc())
            elif sort_column == 4:  # Title
                query = query.order_by(Document.title.asc() if sort_ascending else Document.title.desc())
            
            # Get the documents
            documents = query.all()
            
            # Add to table
            self.queue_table.setRowCount(len(documents))
            
            # Statistics counters
            total_count = len(documents)
            due_today_count = 0
            due_week_count = 0
            overdue_count = 0
            new_count = 0
            
            # Load documents
            for row, document in enumerate(documents):
                # Create title item
                title_item = QTableWidgetItem(document.title)
                title_item.setData(Qt.ItemDataRole.UserRole, document.id)
                
                # Set background color based on priority and favorite status
                if hasattr(document, 'is_favorite') and document.is_favorite:
                    title_item.setBackground(QBrush(QColor(255, 255, 200)))  # Light yellow for favorites
                    # Add a star to indicate favorite
                    title_item.setText("★ " + document.title)
                elif document.priority >= 75:
                    title_item.setBackground(QBrush(QColor(255, 200, 200)))  # Light red for high priority
                elif document.priority >= 50:
                    title_item.setBackground(QBrush(QColor(255, 235, 156)))  # Light orange for medium priority
                    
                self.queue_table.setItem(row, 0, title_item)
                
                # Add priority
                priority_item = QTableWidgetItem(str(document.priority))
                self.queue_table.setItem(row, 1, priority_item)
                
                # Add due date
                if document.next_reading_date:
                    due_date = document.next_reading_date.strftime("%Y-%m-%d")
                    due_item = QTableWidgetItem(due_date)
                    
                    # Calculate days until due
                    days_until_due = (document.next_reading_date - today).days
                    
                    # Set color based on due date
                    if days_until_due < 0:
                        # Overdue
                        due_item.setForeground(QBrush(QColor(255, 0, 0)))
                        overdue_count += 1
                    elif days_until_due == 0:
                        # Due today
                        due_item.setForeground(QBrush(QColor(255, 128, 0)))
                        due_today_count += 1
                    elif days_until_due < 7:
                        # Due this week
                        due_item.setForeground(QBrush(QColor(0, 128, 0)))
                        due_week_count += 1
                else:
                    # New document
                    due_item = QTableWidgetItem("New")
                    due_item.setForeground(QBrush(QColor(0, 0, 255)))
                    new_count += 1
                    
                self.queue_table.setItem(row, 2, due_item)
                
                # Add category
                category_name = "Uncategorized"
                if document.category_id is not None:
                    category = self.db_session.query(Category).get(document.category_id)
                    if category:
                        category_name = category.name
                        
                category_item = QTableWidgetItem(category_name)
                self.queue_table.setItem(row, 3, category_item)
                
                # Add reading count
                reading_count = document.reading_count or 0
                count_item = QTableWidgetItem(str(reading_count))
                self.queue_table.setItem(row, 4, count_item)
            
            # Update statistics
            self.total_label.setText(str(total_count))
            self.due_today_label.setText(str(due_today_count))
            self.due_week_label.setText(str(due_week_count))
            self.overdue_label.setText(str(overdue_count))
            self.new_label.setText(str(new_count))
                
        except Exception as e:
            logger.exception(f"Error loading queue data: {e}")

    def _get_subcategory_ids(self, parent_id, category_ids):
        """Recursively get all subcategory IDs for a given parent category."""
        subcategories = self.db_session.query(Category).filter(Category.parent_id == parent_id).all()
        for subcategory in subcategories:
            category_ids.append(subcategory.id)
            self._get_subcategory_ids(subcategory.id, category_ids)

    def _load_knowledge_tree(self):
        """Load categories into the knowledge tree."""
        try:
            if not hasattr(self, 'knowledge_tree'):
                logger.warning("Knowledge tree not available")
                return
            
            # Get filter settings
            show_empty = self.show_empty_check.isChecked()
            sort_alphabetically = self.sort_alpha_check.isChecked()
            
            # Remember expanded items if possible
            expanded_items = set()
            self._save_expanded_state(self.knowledge_tree.invisibleRootItem(), "", expanded_items)
            
            # Clear existing items
            self.knowledge_tree.clear()
            
            # Add "All Categories" root item
            all_item = QTreeWidgetItem(self.knowledge_tree)
            all_item.setText(0, "All Categories")
            all_item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            all_item.setData(0, Qt.ItemDataRole.UserRole, None)  # No category ID
            
            # Count all documents
            total_count = self.db_session.query(Document).count()
            all_item.setText(1, str(total_count))
            all_item.setForeground(1, self._get_count_color(total_count))
            
            # Add all top-level categories (those with no parent)
            query = self.db_session.query(Category).filter(Category.parent_id == None)
            
            # Apply sorting
            if sort_alphabetically:
                query = query.order_by(Category.name)
            else:
                # Sort by ID (creation order)
                query = query.order_by(Category.id)
            
            top_categories = query.all()
            
            for category in top_categories:
                # Skip categories with no documents if show_empty is False
                if not show_empty:
                    doc_count = self._get_category_document_count(category.id, include_subcategories=True)
                    if doc_count == 0:
                        continue
                
                # Create tree item
                cat_item = self._create_category_tree_item(category)
                
                # Add to tree
                self.knowledge_tree.addTopLevelItem(cat_item)
                
                # Recursively add subcategories
                self._add_subcategories(cat_item, category.id, show_empty, sort_alphabetically)
                
                # Check if this item was previously expanded
                if category.name in expanded_items:
                    cat_item.setExpanded(True)
            
            # Keep "All Categories" expanded
            all_item.setExpanded(True)
            
            # Restore expanded state where possible
            self._restore_expanded_state(self.knowledge_tree.invisibleRootItem(), "", expanded_items)
            
        except Exception as e:
            logger.exception(f"Error loading knowledge tree: {e}")
            # Display error message in tree
            self.knowledge_tree.clear()
            error_item = QTreeWidgetItem(self.knowledge_tree)
            error_item.setText(0, f"Error loading categories: {str(e)}")
            error_item.setForeground(0, QBrush(QColor(255, 0, 0)))

    def _create_category_tree_item(self, category):
        """Create a tree item for a category."""
        item = QTreeWidgetItem()
        item.setText(0, category.name)
        item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
        item.setData(0, Qt.ItemDataRole.UserRole, category.id)
        
        # Count documents directly in this category
        direct_count = self._get_category_document_count(category.id, include_subcategories=False)
        
        # Count total documents including subcategories
        total_count = self._get_category_document_count(category.id, include_subcategories=True)
        
        # Show total count
        item.setText(1, str(total_count))
        item.setForeground(1, self._get_count_color(total_count))
        
        # Make bold if contains documents
        if total_count > 0:
            item.setFont(0, self._get_bold_font())
        
        # Add tooltip with counts explanation
        item.setToolTip(0, f"Direct documents: {direct_count}\nTotal including subcategories: {total_count}")

        return item

    def _save_expanded_state(self, item, path, expanded_items):
        """Recursively save the expanded state of tree items."""
        if not item:
            return
        
        # If this is not the invisible root and is expanded, add to set
        if item is not self.knowledge_tree.invisibleRootItem() and item.isExpanded():
            # Use the text as identifier
            expanded_items.add(item.text(0))
        
        # Process all children
        for i in range(item.childCount()):
            child = item.child(i)
            if child:
                # Get the child path
                child_path = f"{path}/{child.text(0)}" if path else child.text(0)
                self._save_expanded_state(child, child_path, expanded_items)

    def _restore_expanded_state(self, item, path, expanded_items):
        """Recursively restore the expanded state of tree items."""
        if not item:
            return
        
        # If this is not the invisible root and is in expanded set, expand it
        if item is not self.knowledge_tree.invisibleRootItem() and item.text(0) in expanded_items:
            item.setExpanded(True)
        
        # Process all children
        for i in range(item.childCount()):
            child = item.child(i)
            if child:
                # Get the child path
                child_path = f"{path}/{child.text(0)}" if path else child.text(0)
                self._restore_expanded_state(child, child_path, expanded_items)

    def _on_queue_search(self):
        """Handle search in the queue table."""
        query = self.queue_search_box.text().lower()
        if not query:
            # If query is empty, just reload the data
            self._load_queue_data()
            return
            
        # Show only rows that match the query
        for row in range(self.queue_table.rowCount()):
            title = self.queue_table.item(row, 0).text().lower()
            category = self.queue_table.item(row, 3).text().lower()
            
            # Match if query is in title or category
            matches = query in title or query in category
            self.queue_table.setRowHidden(row, not matches)

    def _on_sort_changed(self):
        """Handle changes to the sort order."""
        # Reload queue data with new sort settings
        self._load_queue_data()

    def _clear_queue_filters(self):
        """Clear all filters and reload the queue."""
        self.queue_search_box.clear()
        self.show_favorites_only.setChecked(False)
        self.sort_combo.setCurrentIndex(0)  # Back to Priority
        self.sort_asc_button.setChecked(False)  # Back to descending
        self._load_queue_data()

    def _select_category_by_name(self, category_name):
        """Select a category in the tree by name."""
        try:
            # Iterate through all top-level items
            for i in range(self.knowledge_tree.topLevelItemCount()):
                item = self.knowledge_tree.topLevelItem(i)
                if item.text(0) == category_name:
                    self.knowledge_tree.setCurrentItem(item)
                    return True
                    
            # If not found at top level, search all items
            found = self._find_item_by_text(self.knowledge_tree.invisibleRootItem(), category_name)
            if found:
                self.knowledge_tree.setCurrentItem(found)
                # Ensure parent items are expanded
                parent = found.parent()
                while parent and parent != self.knowledge_tree.invisibleRootItem():
                    parent.setExpanded(True)
                    parent = parent.parent()
                return True
                
            return False
        except Exception as e:
            logger.exception(f"Error selecting category: {e}")
            return False

    def _find_item_by_text(self, parent_item, text):
        """Find a tree item by its text value."""
        # Search direct children
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.text(0) == text:
                return child
                
            # Recursively search grandchildren
            found = self._find_item_by_text(child, text)
            if found:
                return found
                
        return None

    def update_settings(self):
        """Update the UI based on changed settings.
        
        This method is called when settings are changed elsewhere in the application,
        such as when a theme is changed through the settings dialog.
        """
        try:
            logger.debug("Updating QueueView settings")
            
            if hasattr(self, 'settings_manager') and self.settings_manager:
                # Get current theme setting
                theme = self.settings_manager.get_setting('ui', 'theme', 'Default')
                is_custom = self.settings_manager.get_setting('ui', 'custom_theme', False)
                
                logger.debug(f"Applying updated theme: {theme} (custom: {is_custom})")
                
                # For custom themes, ensure "Custom" is selected in combo box
                if is_custom:
                    theme = "Custom"
                
                # Find theme in combo box
                index = self.theme_combo.findText(theme)
                if index >= 0:
                    # Update the combo box to match the current theme
                    self.theme_combo.setCurrentIndex(index)
                else:
                    # If theme not found, update the first item (Default)
                    self.theme_combo.setCurrentIndex(0)
                    # And apply the theme directly
                    self._apply_theme(0)
                    
                # Refresh the queue display with any new settings
                self._load_queue_data()
                    
                # Restore any saved state
                self.restoreState()
                    
                # Apply all styling to ensure complete theme integration
                self._sync_with_application_palette()
        except Exception as e:
            logger.exception(f"Error updating settings in queue view: {e}")
            
        # Return True to indicate the update was processed
        return True

    def _sync_with_application_palette(self):
        """Synchronize the queue view's palette with the application's theme."""
        try:
            theme = self.settings_manager.get_setting('ui', 'theme', 'light')
            if theme is None:
                theme = 'light'
            theme = theme.lower()
            
            # Get the application's palette
            palette = QApplication.palette()
            
            # Set colors based on theme
            if theme == 'dark':
                self.setStyleSheet("""
                    QWidget {
                        background-color: #2b2b2b;
                        color: #ffffff;
                    }
                    QListWidget {
                        background-color: #2b2b2b;
                        color: #ffffff;
                        border: 1px solid #3b3b3b;
                    }
                    QListWidget::item {
                        padding: 5px;
                        border-bottom: 1px solid #3b3b3b;
                    }
                    QListWidget::item:selected {
                        background-color: #3b3b3b;
                        color: #ffffff;
                    }
                """)
            else:  # light theme
                self.setStyleSheet("""
                    QWidget {
                        background-color: #ffffff;
                        color: #000000;
                    }
                    QListWidget {
                        background-color: #ffffff;
                        color: #000000;
                        border: 1px solid #cccccc;
                    }
                    QListWidget::item {
                        padding: 5px;
                        border-bottom: 1px solid #eeeeee;
                    }
                    QListWidget::item:selected {
                        background-color: #e0e0e0;
                        color: #000000;
                    }
                """)
        except Exception as e:
            logger.error(f"Error synchronizing with application palette: {e}")
            # Set a default style if there's an error
            self.setStyleSheet("""
                QWidget {
                    background-color: #ffffff;
                    color: #000000;
                }
            """)

    def _apply_supermemo_styling(self):
        """Apply SuperMemo-specific styling to the queue view."""
        try:
            # SuperMemo typically uses a blue gradient background and gold highlights
            supermemo_style = """
                QTreeWidget, QTableWidget {
                    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #EEF5FD, stop:1 #D6E9FF);
                    alternate-background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E5EFF9, stop:1 #C6DFFF);
                }
                
                QTreeWidget::item:selected, QTableWidget::item:selected {
                    background-color: #FFD700;
                    color: #000000;
                }
                
                QTreeWidget::branch:has-children {
                    border-image: none;
                    image: url(":/icons/branch-closed.png");
                }
                
                QTreeWidget::branch:has-children:open {
                    image: url(":/icons/branch-open.png");
                }
                
                QHeaderView::section {
                    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #D6E9FF, stop:1 #94BADE);
                    border: 1px solid #7BA7CE;
                }
                
                QTabBar::tab:selected {
                    background-color: #FFD700;
                    color: #000000;
                }
            """
            
            # Extend the current stylesheet
            current_style = self.styleSheet()
            self.setStyleSheet(current_style + supermemo_style)
            
            # Set specific colors for knowledge tree items
            for i in range(self.knowledge_tree.topLevelItemCount()):
                self._style_tree_item_supermemo(self.knowledge_tree.topLevelItem(i))
                
        except Exception as e:
            logger.exception(f"Error applying SuperMemo styling: {e}")

    def _style_tree_item_supermemo(self, item):
        """Apply SuperMemo styling to a tree item recursively."""
        if not item:
            return
            
        # Get document count
        count_str = item.text(1)
        try:
            count = int(count_str) if count_str else 0
        except ValueError:
            count = 0
            
        # Style based on document count
        if count > 50:
            item.setForeground(0, QBrush(QColor("#8B0000")))  # Dark red for very active
            item.setFont(0, self._get_supermemo_font(True, 12))
        elif count > 20:
            item.setForeground(0, QBrush(QColor("#A52A2A")))  # Brown-red for active
            item.setFont(0, self._get_supermemo_font(True, 11))
        elif count > 10:
            item.setForeground(0, QBrush(QColor("#000080")))  # Navy for moderately active
            item.setFont(0, self._get_supermemo_font(True, 10))
        elif count > 0:
            item.setForeground(0, QBrush(QColor("#006400")))  # Dark green for some content
            item.setFont(0, self._get_supermemo_font(False, 10))
        else:
            item.setForeground(0, QBrush(QColor("#696969")))  # Gray for no content
            item.setFont(0, self._get_supermemo_font(False, 9))
            
        # Process children recursively
        for i in range(item.childCount()):
            self._style_tree_item_supermemo(item.child(i))

    def _get_supermemo_font(self, bold=False, size=10):
        """Get a font styled for SuperMemo theme."""
        font = QFont("Arial")
        font.setPointSize(size)
        font.setBold(bold)
        return font

    def set_current_document(self, document_id):
        """Set the current document in the queue view.
        
        This will select the document in the queue table if it's present,
        or add it to the queue if it's not already there.
        
        Args:
            document_id: The ID of the document to set as current
        """
        try:
            if document_id is None:
                return
                
            logger.debug(f"Setting current document to ID: {document_id}")
            
            # Search for the document in the current queue
            found = False
            for row in range(self.queue_table.rowCount()):
                item_id = self.queue_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if item_id == document_id:
                    # Select this row
                    self.queue_table.selectRow(row)
                    found = True
                    break
                    
            if not found:
                # Document not in current queue - check if it exists in the database
                document = self.db_session.query(Document).get(document_id)
                if document:
                    # Add a temporary entry for this document at the top of the queue
                    self._add_document_to_queue(document, temporary=True)
                    # Select the first row (the one we just added)
                    self.queue_table.selectRow(0)
                    
        except Exception as e:
            logger.exception(f"Error setting current document: {e}")

    def _add_document_to_queue(self, document, temporary=False):
        """Add a document to the queue table.
        
        Args:
            document: The Document object to add
            temporary: If True, this document is being added temporarily
                      and will be marked with a visual indicator
        """
        try:
            # Insert at the top
            self.queue_table.insertRow(0)
            
            # Create title item
            title_item = QTableWidgetItem(document.title)
            title_item.setData(Qt.ItemDataRole.UserRole, document.id)
            
            # If temporary, mark with a different color
            if temporary:
                title_item.setBackground(QBrush(QColor(230, 230, 255)))  # Light blue background
                title_item.setToolTip("Document added temporarily to the queue")
            
            # Set background color based on priority
            elif document.priority >= 75:
                title_item.setBackground(QBrush(QColor(255, 200, 200)))  # Light red for high priority
            elif document.priority >= 50:
                title_item.setBackground(QBrush(QColor(255, 235, 156)))  # Light orange for medium priority
                
            self.queue_table.setItem(0, 0, title_item)
            
            # Add priority
            priority_item = QTableWidgetItem(str(document.priority))
            self.queue_table.setItem(0, 1, priority_item)
            
            # Add due date
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if document.next_reading_date:
                due_date = document.next_reading_date.strftime("%Y-%m-%d")
                due_item = QTableWidgetItem(due_date)
                
                # Calculate days until due
                days_until_due = (document.next_reading_date - today).days
                
                # Set color based on due date
                if days_until_due < 0:
                    # Overdue
                    due_item.setForeground(QBrush(QColor(255, 0, 0)))
                elif days_until_due == 0:
                    # Due today
                    due_item.setForeground(QBrush(QColor(255, 128, 0)))
                elif days_until_due < 7:
                    # Due this week
                    due_item.setForeground(QBrush(QColor(0, 128, 0)))
            else:
                # New document
                due_item = QTableWidgetItem("New")
                due_item.setForeground(QBrush(QColor(0, 0, 255)))
                
            self.queue_table.setItem(0, 2, due_item)
            
            # Add category
            category_name = "Uncategorized"
            if document.category_id is not None:
                category = self.db_session.query(Category).get(document.category_id)
                if category:
                    category_name = category.name
                    
            category_item = QTableWidgetItem(category_name)
            self.queue_table.setItem(0, 3, category_item)
            
            # Add reading count
            reading_count = document.reading_count or 0
            count_item = QTableWidgetItem(str(reading_count))
            self.queue_table.setItem(0, 4, count_item)
            
            # Update the statistics
            total_count = int(self.total_label.text()) + 1
            self.total_label.setText(str(total_count))
            
            if document.next_reading_date is None:
                new_count = int(self.new_label.text()) + 1
                self.new_label.setText(str(new_count))
            elif document.next_reading_date == today:
                due_today = int(self.due_today_label.text()) + 1
                self.due_today_label.setText(str(due_today))
            elif document.next_reading_date < today:
                overdue = int(self.overdue_label.text()) + 1
                self.overdue_label.setText(str(overdue))
            elif document.next_reading_date < (today + timedelta(days=7)):
                due_week = int(self.due_week_label.text()) + 1
                self.due_week_label.setText(str(due_week))
                
        except Exception as e:
            logger.exception(f"Error adding document to queue: {e}")
