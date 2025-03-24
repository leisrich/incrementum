"""
Category Manager Dialog for Incrementum
Allows users to create, edit, delete, and organize categories
"""

import logging
from typing import Optional, Dict, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, 
    QPushButton, QLineEdit, QLabel, QMessageBox, QMenu, QFormLayout, 
    QWidget, QInputDialog, QColorDialog, QComboBox, QDialogButtonBox, 
    QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize
from PyQt6.QtGui import QColor, QIcon, QCursor

from sqlalchemy import select, func, update, delete
from sqlalchemy.exc import SQLAlchemyError

from core.knowledge_base.models import Category, Document, Extract, LearningItem

logger = logging.getLogger(__name__)

class CategoryManagerDialog(QDialog):
    """Dialog for managing document/extract categories."""
    
    def __init__(self, db_session, parent=None):
        super().__init__(parent)
        
        self.db_session = db_session
        self.modified = False
        
        self.setWindowTitle("Category Manager")
        self.setMinimumSize(800, 600)
        
        self._create_ui()
        self._load_categories()
        
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Instruction label
        instruction_label = QLabel(
            "Manage your document and extract categories. "
            "Right-click on categories for additional options."
        )
        instruction_label.setWordWrap(True)
        main_layout.addWidget(instruction_label)
        
        # Create split layout for tree and details
        split_layout = QHBoxLayout()
        
        # Category tree
        tree_layout = QVBoxLayout()
        tree_layout.addWidget(QLabel("Categories:"))
        
        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderLabels(["Category", "Documents", "Extracts"])
        self.category_tree.setColumnWidth(0, 300)
        self.category_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.category_tree.customContextMenuRequested.connect(self._show_context_menu)
        self.category_tree.itemSelectionChanged.connect(self._on_category_selected)
        
        tree_layout.addWidget(self.category_tree)
        
        # Add category button
        add_layout = QHBoxLayout()
        self.add_category_button = QPushButton("Add Root Category")
        self.add_category_button.clicked.connect(self._on_add_root_category)
        add_layout.addWidget(self.add_category_button)
        
        self.add_subcategory_button = QPushButton("Add Subcategory")
        self.add_subcategory_button.clicked.connect(self._on_add_subcategory)
        self.add_subcategory_button.setEnabled(False)
        add_layout.addWidget(self.add_subcategory_button)
        
        tree_layout.addLayout(add_layout)
        
        split_layout.addLayout(tree_layout, 2)
        
        # Details panel
        details_layout = QVBoxLayout()
        details_layout.addWidget(QLabel("Category Details:"))
        
        self.details_widget = QWidget()
        self.details_form = QFormLayout(self.details_widget)
        
        # Category name
        self.category_name = QLineEdit()
        self.details_form.addRow("Name:", self.category_name)
        
        # Category color
        color_layout = QHBoxLayout()
        self.category_color = QLineEdit()
        self.category_color.setReadOnly(True)
        color_layout.addWidget(self.category_color)
        
        self.color_button = QPushButton("Choose...")
        self.color_button.clicked.connect(self._on_choose_color)
        color_layout.addWidget(self.color_button)
        
        self.details_form.addRow("Color:", color_layout)
        
        # Parent category
        self.parent_category = QComboBox()
        self.details_form.addRow("Parent:", self.parent_category)
        
        # Save button
        self.save_details_button = QPushButton("Save Changes")
        self.save_details_button.clicked.connect(self._on_save_details)
        self.save_details_button.setEnabled(False)
        self.details_form.addRow("", self.save_details_button)
        
        details_layout.addWidget(self.details_widget)
        
        # Category statistics
        stats_group = QGroupBox("Statistics")
        stats_layout = QFormLayout(stats_group)
        
        self.documents_count = QLabel("0")
        stats_layout.addRow("Documents:", self.documents_count)
        
        self.extracts_count = QLabel("0")
        stats_layout.addRow("Extracts:", self.extracts_count)
        
        self.items_count = QLabel("0")
        stats_layout.addRow("Learning Items:", self.items_count)
        
        details_layout.addWidget(stats_group)
        
        # Quick actions
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions_group)
        
        self.review_docs_button = QPushButton("Review Documents in Category")
        self.review_docs_button.clicked.connect(self._on_review_documents)
        self.review_docs_button.setEnabled(False)
        actions_layout.addWidget(self.review_docs_button)
        
        self.review_extracts_button = QPushButton("Review Extracts in Category")
        self.review_extracts_button.clicked.connect(self._on_review_extracts)
        self.review_extracts_button.setEnabled(False)
        actions_layout.addWidget(self.review_extracts_button)
        
        self.merge_button = QPushButton("Merge with Another Category...")
        self.merge_button.clicked.connect(self._on_merge_categories)
        self.merge_button.setEnabled(False)
        actions_layout.addWidget(self.merge_button)
        
        details_layout.addWidget(actions_group)
        details_layout.addStretch()
        
        split_layout.addLayout(details_layout, 1)
        
        main_layout.addLayout(split_layout)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        main_layout.addWidget(button_box)
        
        # Disable details panel initially
        self.details_widget.setEnabled(False)
        
    def _load_categories(self):
        """Load categories into the tree widget."""
        try:
            self.category_tree.clear()
            self.parent_category.clear()
            
            # Add "None" option for parent category
            self.parent_category.addItem("(No Parent)", None)
            
            # Get all categories
            categories = self.db_session.execute(
                select(Category)
            ).scalars().all()
            
            # Create a dictionary of categories by id
            category_dict = {category.id: category for category in categories}
            
            # Create a dictionary of TreeWidgetItems by category id
            self.tree_items = {}
            
            # First, add all root categories (no parent)
            for category in categories:
                if category.parent_id is None:
                    item = QTreeWidgetItem([category.name, "0", "0"])
                    item.setData(0, Qt.ItemDataRole.UserRole, category.id)
                    self.category_tree.addTopLevelItem(item)
                    self.tree_items[category.id] = item
                    
                    # Add to parent category combo box
                    self.parent_category.addItem(category.name, category.id)
            
            # Then, add all child categories
            for category in categories:
                if category.parent_id is not None and category.parent_id in self.tree_items:
                    parent_item = self.tree_items[category.parent_id]
                    item = QTreeWidgetItem([category.name, "0", "0"])
                    item.setData(0, Qt.ItemDataRole.UserRole, category.id)
                    parent_item.addChild(item)
                    self.tree_items[category.id] = item
                    
                    # Add to parent category combo box with indentation
                    parent_name = category_dict[category.parent_id].name
                    self.parent_category.addItem(f"  {category.name} (under {parent_name})", category.id)
            
            # Load document and extract counts
            self._load_category_counts()
            
            # Expand all items
            self.category_tree.expandAll()
            
            # Update user categories in settings
            try:
                from core.utils.category_helper import update_user_categories
                update_user_categories(self.db_session)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to update user categories in settings: {e}")
            
        except Exception as e:
            logger.exception(f"Error loading categories: {e}")
            QMessageBox.warning(self, "Error", f"Error loading categories: {str(e)}")
    
    def _load_category_counts(self):
        """Load document and extract counts for each category."""
        try:
            # Get document counts by category
            doc_counts = self.db_session.execute(
                select(Category.id, func.count(Document.id))
                .outerjoin(Document, Document.category_id == Category.id)
                .group_by(Category.id)
            ).all()
            
            doc_count_dict = {cat_id: count for cat_id, count in doc_counts}
            
            # Get extract counts by category
            extract_counts = self.db_session.execute(
                select(Category.id, func.count(Extract.id))
                .outerjoin(Extract, Extract.category_id == Category.id)
                .group_by(Category.id)
            ).all()
            
            extract_count_dict = {cat_id: count for cat_id, count in extract_counts}
            
            # Update tree items with counts
            for cat_id, item in self.tree_items.items():
                doc_count = doc_count_dict.get(cat_id, 0)
                extract_count = extract_count_dict.get(cat_id, 0)
                
                item.setText(1, str(doc_count))
                item.setText(2, str(extract_count))
        
        except Exception as e:
            logger.exception(f"Error loading category counts: {e}")
    
    def _show_context_menu(self, position):
        """Show context menu for the category tree."""
        item = self.category_tree.itemAt(position)
        if not item:
            return
            
        # Get category ID
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        # Create context menu
        menu = QMenu(self)
        
        # Add actions
        add_subcategory = menu.addAction("Add Subcategory")
        edit_action = menu.addAction("Edit Category")
        menu.addSeparator()
        rename_action = menu.addAction("Rename")
        change_color_action = menu.addAction("Change Color")
        menu.addSeparator()
        
        if item.parent():
            move_up_action = menu.addAction("Move Up")
            move_root_action = menu.addAction("Make Root Category")
        else:
            move_up_action = None
            move_root_action = None
            
        menu.addSeparator()
        delete_action = menu.addAction("Delete Category")
        
        # Show menu and get selected action
        action = menu.exec(QCursor.pos())
        
        # Handle action
        if action == add_subcategory:
            self._on_add_subcategory()
        elif action == edit_action:
            self._on_edit_category()
        elif action == rename_action:
            self._on_rename_category()
        elif action == change_color_action:
            self._on_change_color()
        elif action == delete_action:
            self._on_delete_category()
        elif action == move_up_action:
            self._on_move_category_up()
        elif action == move_root_action:
            self._on_make_root_category()
    
    def _on_category_selected(self):
        """Handle category selection in the tree."""
        items = self.category_tree.selectedItems()
        if not items:
            self.details_widget.setEnabled(False)
            self.add_subcategory_button.setEnabled(False)
            self.review_docs_button.setEnabled(False)
            self.review_extracts_button.setEnabled(False)
            self.merge_button.setEnabled(False)
            return
            
        self.details_widget.setEnabled(True)
        self.add_subcategory_button.setEnabled(True)
        self.save_details_button.setEnabled(True)
        self.review_docs_button.setEnabled(True)
        self.review_extracts_button.setEnabled(True)
        self.merge_button.setEnabled(True)
        
        # Get selected category
        item = items[0]
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        try:
            # Load category details
            category = self.db_session.execute(
                select(Category).where(Category.id == category_id)
            ).scalar_one_or_none()
            
            if category:
                # Update details panel
                self.category_name.setText(category.name)
                
                if category.color:
                    self.category_color.setText(category.color)
                    self.category_color.setStyleSheet(f"background-color: {category.color}")
                else:
                    self.category_color.setText("#FFFFFF")
                    self.category_color.setStyleSheet("background-color: #FFFFFF")
                
                # Set parent category
                parent_index = 0  # Default to "No Parent"
                if category.parent_id is not None:
                    for i in range(self.parent_category.count()):
                        if self.parent_category.itemData(i) == category.parent_id:
                            parent_index = i
                            break
                
                self.parent_category.setCurrentIndex(parent_index)
                
                # Update statistics
                self.documents_count.setText(item.text(1))
                self.extracts_count.setText(item.text(2))
                
                # Get learning items count
                items_count = self.db_session.execute(
                    select(func.count(LearningItem.id))
                    .join(Extract, Extract.id == LearningItem.extract_id)
                    .where(Extract.category_id == category_id)
                ).scalar_one()
                
                self.items_count.setText(str(items_count))
        
        except Exception as e:
            logger.exception(f"Error loading category details: {e}")
            QMessageBox.warning(self, "Error", f"Error loading category details: {str(e)}")
    
    def _on_add_root_category(self):
        """Add a new root category."""
        name, ok = QInputDialog.getText(self, "New Root Category", "Category name:")
        if ok and name.strip():
            try:
                # Create new category using helper function
                from core.utils.category_helper import create_category
                create_category(self.db_session, name.strip())
                
                # Reload categories
                self._load_categories()
                self.modified = True
                
            except Exception as e:
                self.db_session.rollback()
                logger.exception(f"Error adding category: {e}")
                QMessageBox.warning(self, "Error", f"Error adding category: {str(e)}")
    
    def _on_add_subcategory(self):
        """Add a subcategory to the selected category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        parent_item = items[0]
        parent_id = parent_item.data(0, Qt.ItemDataRole.UserRole)
        
        name, ok = QInputDialog.getText(
            self, "New Subcategory", 
            f"Subcategory name (under {parent_item.text(0)}):"
        )
        
        if ok and name.strip():
            try:
                # Create new subcategory using helper function
                from core.utils.category_helper import create_category
                create_category(self.db_session, name.strip(), parent_id)
                
                # Reload categories
                self._load_categories()
                self.modified = True
                
            except Exception as e:
                self.db_session.rollback()
                logger.exception(f"Error adding subcategory: {e}")
                QMessageBox.warning(self, "Error", f"Error adding subcategory: {str(e)}")
    
    def _on_edit_category(self):
        """Edit the selected category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        # Select the category in the details panel
        self._on_category_selected()
    
    def _on_rename_category(self):
        """Rename the selected category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        name, ok = QInputDialog.getText(
            self, "Rename Category", 
            "New category name:", 
            text=item.text(0)
        )
        
        if ok and name.strip():
            try:
                # Rename category using helper function
                from core.utils.category_helper import rename_category
                rename_category(self.db_session, category_id, name.strip())
                
                # Reload categories
                self._load_categories()
                self.modified = True
                
            except Exception as e:
                self.db_session.rollback()
                logger.exception(f"Error renaming category: {e}")
                QMessageBox.warning(self, "Error", f"Error renaming category: {str(e)}")
    
    def _on_change_color(self):
        """Change the color of the selected category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        try:
            # Get current color
            category = self.db_session.execute(
                select(Category).where(Category.id == category_id)
            ).scalar_one()
            
            current_color = QColor(category.color) if category.color else QColor("#FFFFFF")
            
            # Show color dialog
            color = QColorDialog.getColor(current_color, self, "Select Category Color")
            
            if color.isValid():
                # Update category color
                category.color = color.name()
                self.db_session.commit()
                
                # Update details panel if this category is selected
                if self.details_widget.isEnabled():
                    self.category_color.setText(color.name())
                    self.category_color.setStyleSheet(f"background-color: {color.name()}")
                
                self.modified = True
                
        except Exception as e:
            self.db_session.rollback()
            logger.exception(f"Error changing category color: {e}")
            QMessageBox.warning(self, "Error", f"Error changing category color: {str(e)}")
    
    def _on_delete_category(self):
        """Delete the selected category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        try:
            # Check if category has documents or extracts
            doc_count = int(item.text(1))
            extract_count = int(item.text(2))
            
            # Check if category has subcategories
            child_count = item.childCount()
            
            # Build confirmation message
            msg = f"Are you sure you want to delete the category '{item.text(0)}'?"
            
            if child_count > 0:
                msg += f"\n\nThis will also delete {child_count} subcategories."
                
            if doc_count > 0 or extract_count > 0:
                msg += f"\n\nThis will remove the category from {doc_count} documents and {extract_count} extracts."
            
            # Confirm deletion
            reply = QMessageBox.question(
                self, "Confirm Deletion", msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Delete category using helper function
                from core.utils.category_helper import delete_category
                delete_category(self.db_session, category_id, force=True)
                
                # Reload categories
                self._load_categories()
                
                # Clear details panel
                self.details_widget.setEnabled(False)
                self.modified = True
                
        except Exception as e:
            self.db_session.rollback()
            logger.exception(f"Error deleting category: {e}")
            QMessageBox.warning(self, "Error", f"Error deleting category: {str(e)}")
    
    def _on_move_category_up(self):
        """Move a category up one level in the hierarchy."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        if not item.parent():
            return  # Already a root category
            
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        try:
            # Get parent's parent ID
            parent_item = item.parent()
            parent_category_id = parent_item.data(0, Qt.ItemDataRole.UserRole)
            
            category = self.db_session.execute(
                select(Category).where(Category.id == category_id)
            ).scalar_one()
            
            parent_category = self.db_session.execute(
                select(Category).where(Category.id == parent_category_id)
            ).scalar_one()
            
            # Set new parent
            category.parent_id = parent_category.parent_id
            self.db_session.commit()
            
            # Reload categories
            self._load_categories()
            self.modified = True
            
        except Exception as e:
            self.db_session.rollback()
            logger.exception(f"Error moving category: {e}")
            QMessageBox.warning(self, "Error", f"Error moving category: {str(e)}")
    
    def _on_make_root_category(self):
        """Make the selected category a root category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        if not item.parent():
            return  # Already a root category
            
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        try:
            # Set parent to None
            category = self.db_session.execute(
                select(Category).where(Category.id == category_id)
            ).scalar_one()
            
            category.parent_id = None
            self.db_session.commit()
            
            # Reload categories
            self._load_categories()
            self.modified = True
            
        except Exception as e:
            self.db_session.rollback()
            logger.exception(f"Error making root category: {e}")
            QMessageBox.warning(self, "Error", f"Error making root category: {str(e)}")
    
    def _on_choose_color(self):
        """Choose a color for the selected category."""
        current_color = QColor(self.category_color.text()) if self.category_color.text() else QColor("#FFFFFF")
        
        color = QColorDialog.getColor(current_color, self, "Select Category Color")
        
        if color.isValid():
            self.category_color.setText(color.name())
            self.category_color.setStyleSheet(f"background-color: {color.name()}")
    
    def _on_save_details(self):
        """Save changes to the selected category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        try:
            # Get category
            category = self.db_session.execute(
                select(Category).where(Category.id == category_id)
            ).scalar_one()
            
            # Update category
            category.name = self.category_name.text().strip()
            category.color = self.category_color.text()
            
            # Set parent category
            new_parent_id = self.parent_category.currentData()
            
            # Check if new parent would create a cycle
            if new_parent_id == category_id:
                QMessageBox.warning(
                    self, "Invalid Parent", 
                    "A category cannot be its own parent."
                )
                return
                
            # Check if new parent is a descendant of this category
            if new_parent_id is not None:
                parent = self.db_session.execute(
                    select(Category).where(Category.id == new_parent_id)
                ).scalar_one()
                
                ancestor_id = parent.parent_id
                while ancestor_id is not None:
                    if ancestor_id == category_id:
                        QMessageBox.warning(
                            self, "Invalid Parent", 
                            "Cannot set a descendant category as parent."
                        )
                        return
                        
                    ancestor = self.db_session.execute(
                        select(Category).where(Category.id == ancestor_id)
                    ).scalar_one_or_none()
                    
                    if not ancestor:
                        break
                        
                    ancestor_id = ancestor.parent_id
            
            category.parent_id = new_parent_id
            self.db_session.commit()
            
            # Reload categories
            self._load_categories()
            
            # Find and select the updated category
            for i in range(self.category_tree.topLevelItemCount()):
                self._find_and_select_category(self.category_tree.topLevelItem(i), category_id)
                
            self.modified = True
            
            QMessageBox.information(
                self, "Success", 
                "Category details saved successfully."
            )
            
        except Exception as e:
            self.db_session.rollback()
            logger.exception(f"Error saving category details: {e}")
            QMessageBox.warning(self, "Error", f"Error saving category details: {str(e)}")
    
    def _find_and_select_category(self, item, category_id):
        """Recursively find and select a category in the tree."""
        if item.data(0, Qt.ItemDataRole.UserRole) == category_id:
            self.category_tree.setCurrentItem(item)
            return True
            
        for i in range(item.childCount()):
            if self._find_and_select_category(item.child(i), category_id):
                return True
                
        return False
    
    def _on_review_documents(self):
        """Open a review session for documents in the selected category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        if int(item.text(1)) == 0:
            QMessageBox.information(
                self, "No Documents", 
                "This category does not contain any documents to review."
            )
            return
            
        # Signal parent to start review session for this category
        self.parent().start_category_review(category_id, "document")
        self.accept()
    
    def _on_review_extracts(self):
        """Open a review session for extracts in the selected category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        if int(item.text(2)) == 0:
            QMessageBox.information(
                self, "No Extracts", 
                "This category does not contain any extracts to review."
            )
            return
            
        # Signal parent to start review session for this category
        self.parent().start_category_review(category_id, "extract")
        self.accept()
    
    def _on_merge_categories(self):
        """Merge the selected category with another category."""
        items = self.category_tree.selectedItems()
        if not items:
            return
            
        item = items[0]
        category_id = item.data(0, Qt.ItemDataRole.UserRole)
        
        # Create dialog for selecting merge target
        dialog = QDialog(self)
        dialog.setWindowTitle("Merge Categories")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel(f"Merge '{item.text(0)}' into:"))
        
        # Create category tree for selecting merge target
        target_tree = QTreeWidget()
        target_tree.setHeaderLabels(["Category"])
        layout.addWidget(target_tree)
        
        # Populate tree excluding selected category and its descendants
        self._populate_merge_target_tree(target_tree, category_id)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        # Show dialog
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get selected target
            target_items = target_tree.selectedItems()
            if not target_items:
                return
                
            target_item = target_items[0]
            target_id = target_item.data(0, Qt.ItemDataRole.UserRole)
            
            # Confirm merge
            reply = QMessageBox.question(
                self, "Confirm Merge", 
                f"Are you sure you want to merge '{item.text(0)}' into '{target_item.text(0)}'?\n\n"
                "This will move all documents and extracts to the target category.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self._merge_categories(category_id, target_id)
    
    def _populate_merge_target_tree(self, tree, exclude_id):
        """Populate a tree with categories, excluding the specified category and its descendants."""
        try:
            # Get all categories
            categories = self.db_session.execute(
                select(Category)
            ).scalars().all()
            
            # Create a dictionary of categories by id
            category_dict = {category.id: category for category in categories}
            
            # Get descendants of exclude_id
            exclude_ids = self._get_category_descendants(exclude_id, category_dict)
            exclude_ids.add(exclude_id)
            
            # Create a dictionary of TreeWidgetItems by category id
            tree_items = {}
            
            # First, add all root categories (no parent)
            for category in categories:
                if category.id in exclude_ids:
                    continue
                    
                if category.parent_id is None:
                    item = QTreeWidgetItem([category.name])
                    item.setData(0, Qt.ItemDataRole.UserRole, category.id)
                    tree.addTopLevelItem(item)
                    tree_items[category.id] = item
            
            # Then, add all child categories
            for category in categories:
                if category.id in exclude_ids:
                    continue
                    
                if category.parent_id is not None and category.parent_id in tree_items:
                    parent_item = tree_items[category.parent_id]
                    item = QTreeWidgetItem([category.name])
                    item.setData(0, Qt.ItemDataRole.UserRole, category.id)
                    parent_item.addChild(item)
                    tree_items[category.id] = item
            
            # Expand all items
            tree.expandAll()
            
        except Exception as e:
            logger.exception(f"Error populating merge target tree: {e}")
            QMessageBox.warning(self, "Error", f"Error populating merge target tree: {str(e)}")
    
    def _get_category_descendants(self, category_id, category_dict):
        """Recursively get all descendants of a category."""
        descendants = set()
        
        for cat_id, category in category_dict.items():
            if category.parent_id == category_id:
                descendants.add(cat_id)
                descendants.update(self._get_category_descendants(cat_id, category_dict))
                
        return descendants
    
    def _merge_categories(self, source_id, target_id):
        """Merge source category into target category."""
        try:
            # Update documents
            self.db_session.execute(
                update(Document)
                .where(Document.category_id == source_id)
                .values(category_id=target_id)
            )
            
            # Update extracts
            self.db_session.execute(
                update(Extract)
                .where(Extract.category_id == source_id)
                .values(category_id=target_id)
            )
            
            # Update child categories
            self.db_session.execute(
                update(Category)
                .where(Category.parent_id == source_id)
                .values(parent_id=target_id)
            )
            
            # Delete source category
            self.db_session.execute(
                delete(Category)
                .where(Category.id == source_id)
            )
            
            self.db_session.commit()
            
            # Reload categories
            self._load_categories()
            
            # Clear details panel
            self.details_widget.setEnabled(False)
            self.modified = True
            
            QMessageBox.information(
                self, "Success", 
                "Categories merged successfully."
            )
            
        except Exception as e:
            self.db_session.rollback()
            logger.exception(f"Error merging categories: {e}")
            QMessageBox.warning(self, "Error", f"Error merging categories: {str(e)}")
    
    def accept(self):
        """Handle dialog acceptance."""
        super().accept()
        return self.modified 