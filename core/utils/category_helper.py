# core/utils/category_helper.py

from typing import List, Dict, Any, Set, Optional
import logging

from core.knowledge_base.models import Category
from core.utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

def get_all_categories(db_session, include_user_categories=True, sort_by_name=True) -> List[Category]:
    """
    Retrieve all categories from the database and optionally include user-created categories from settings.
    
    Args:
        db_session: Database session
        include_user_categories: Whether to include user-created categories from settings
        sort_by_name: Whether to sort categories by name
        
    Returns:
        List of Category objects
    """
    # Get categories from database
    categories = db_session.query(Category).all()
    
    # Get user-created categories from settings if enabled
    if include_user_categories:
        try:
            settings = SettingsManager()
            user_categories = settings.get_setting("general", "user_categories", [])
            
            # Create a set of existing category IDs to avoid duplicates
            existing_category_ids = {category.id for category in categories}
            
            # Add user categories that don't exist in the database
            for user_category in user_categories:
                category_id = user_category.get("id")
                if category_id and category_id not in existing_category_ids:
                    # Create a temporary Category object
                    temp_category = Category(
                        id=category_id,
                        name=user_category.get("name", f"Category {category_id}"),
                        parent_id=user_category.get("parent_id")
                    )
                    categories.append(temp_category)
                    existing_category_ids.add(category_id)
        except Exception as e:
            logger.error(f"Failed to load user categories: {e}")
    
    # Sort categories by name if requested
    if sort_by_name:
        categories.sort(key=lambda c: c.name)
    
    return categories

def populate_category_combo(combo_box, db_session, include_all_option=True, 
                           all_text="All Categories", current_category_id=None):
    """
    Populate a combo box with categories, including user-created ones.
    
    Args:
        combo_box: QComboBox to populate
        db_session: Database session
        include_all_option: Whether to include "All Categories" as first option
        all_text: Text for the "All Categories" option
        current_category_id: ID of category to select after populating
    """
    # Clear current items
    combo_box.clear()
    
    # Add "All Categories" option if requested
    if include_all_option:
        combo_box.addItem(all_text, None)
    
    # Get all categories including user-created ones
    categories = get_all_categories(db_session)
    
    # Add to combo box
    for category in categories:
        combo_box.addItem(category.name, category.id)
    
    # Set current category if specified
    if current_category_id is not None:
        # Find index of the category with matching ID
        for i in range(combo_box.count()):
            if combo_box.itemData(i) == current_category_id:
                combo_box.setCurrentIndex(i)
                break

def update_user_categories(db_session):
    """
    Update user categories in settings based on database categories.
    
    Args:
        db_session: Database session
    """
    try:
        # Get categories from database
        categories = db_session.query(Category).all()
        
        # Create list of category information
        user_categories = []
        for category in categories:
            user_categories.append({
                "id": category.id,
                "name": category.name,
                "parent_id": category.parent_id
            })
        
        # Save to settings
        settings = SettingsManager()
        settings.set_setting("general", "user_categories", user_categories)
        settings.save_settings()
    except Exception as e:
        logger.error(f"Failed to update user categories in settings: {e}") 

def create_category(db_session, name, parent_id=None):
    """
    Create a new category and update user categories in settings.
    
    Args:
        db_session: Database session
        name: Name of the new category
        parent_id: ID of the parent category (None for root category)
        
    Returns:
        The newly created Category object
    """
    try:
        # Create new category
        category = Category(name=name, parent_id=parent_id)
        db_session.add(category)
        db_session.commit()
        
        # Update user categories
        update_user_categories(db_session)
        
        return category
    except Exception as e:
        db_session.rollback()
        logger.error(f"Failed to create category: {e}")
        raise 

def rename_category(db_session, category_id, new_name):
    """
    Rename a category and update user categories in settings.
    
    Args:
        db_session: Database session
        category_id: ID of the category to rename
        new_name: New name for the category
        
    Returns:
        The updated Category object or None if not found
    """
    try:
        # Find the category
        category = db_session.query(Category).get(category_id)
        if not category:
            logger.error(f"Category with ID {category_id} not found")
            return None
            
        # Update the name
        category.name = new_name
        db_session.commit()
        
        # Update user categories
        update_user_categories(db_session)
        
        return category
    except Exception as e:
        db_session.rollback()
        logger.error(f"Failed to rename category: {e}")
        raise 

def delete_category(db_session, category_id, force=False):
    """
    Delete a category and update user categories in settings.
    
    Args:
        db_session: Database session
        category_id: ID of the category to delete
        force: If True, also delete any child categories and reassign documents
        
    Returns:
        True if successful, False otherwise
        
    Raises:
        ValueError: If the category has children and force is False
    """
    try:
        # Find the category
        category = db_session.query(Category).get(category_id)
        if not category:
            logger.error(f"Category with ID {category_id} not found")
            return False
        
        # Check for child categories
        child_count = db_session.query(Category).filter(Category.parent_id == category_id).count()
        if child_count > 0 and not force:
            raise ValueError(f"Category has {child_count} child categories. Set force=True to delete anyway.")
        
        # Import Document class here to avoid circular imports
        from core.knowledge_base.models import Document
        
        # Update documents to remove category
        db_session.query(Document).filter(
            Document.category_id == category_id
        ).update({Document.category_id: None})
        
        # If force is True, also handle child categories
        if force and child_count > 0:
            # Get all child categories
            child_categories = db_session.query(Category).filter(Category.parent_id == category_id).all()
            
            # Delete each child category
            for child in child_categories:
                delete_category(db_session, child.id, True)  # Recursive call with force=True
        
        # Delete the category
        db_session.delete(category)
        db_session.commit()
        
        # Update user categories
        update_user_categories(db_session)
        
        return True
    except Exception as e:
        db_session.rollback()
        logger.error(f"Failed to delete category: {e}")
        raise 