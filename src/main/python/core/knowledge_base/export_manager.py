# core/knowledge_base/export_manager.py

import os
import json
import logging
import zipfile
import tempfile
import shutil
from typing import Dict, Any, List, Tuple, Optional, Set, Union
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session
from core.knowledge_base.models import Document, Category, Extract, LearningItem, Tag, ReviewLog
from core.knowledge_base.backup_manager import BackupManager

logger = logging.getLogger(__name__)

class ExportManager:
    """
    Manager for exporting and importing knowledge items.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        self.backup_manager = BackupManager(db_session)
    
    def create_backup(self, include_files: bool = True) -> Optional[str]:
        """
        Create a backup of the database and optionally document files.
        
        Args:
            include_files: Whether to include document files in the backup
            
        Returns:
            Path to the backup file, or None if backup failed
        """
        return self.backup_manager.create_backup(include_files)
    
    def get_backup_list(self) -> List[Dict[str, Any]]:
        """
        Get a list of available backups.
        
        Returns:
            List of dictionaries with backup information
        """
        return self.backup_manager.get_backup_list()
    
    def restore_backup(self, backup_path: str) -> bool:
        """
        Restore a backup.
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            True if restoration successful, False otherwise
        """
        return self.backup_manager.restore_backup(backup_path)
    
    def delete_backup(self, backup_path: str) -> bool:
        """
        Delete a backup file.
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            True if deletion successful, False otherwise
        """
        return self.backup_manager.delete_backup(backup_path)
    
    def export_extracts(self, extract_ids: List[int], filepath: str, include_learning_items: bool = True) -> bool:
        """
        Export extracts to a file.
        
        Args:
            extract_ids: List of extract IDs to export
            filepath: Path to save the export file
            include_learning_items: Whether to include linked learning items
            
        Returns:
            True if export successful, False otherwise
        """
        try:
            # Get extracts
            extracts = self.db_session.query(Extract).filter(Extract.id.in_(extract_ids)).all()
            if not extracts:
                logger.error(f"No extracts found with IDs: {extract_ids}")
                return False
            
            # Build export data
            export_data = {
                'version': '1.0',
                'export_date': datetime.utcnow().isoformat(),
                'extracts': []
            }
            
            # Fill export data
            for extract in extracts:
                extract_data = {
                    'content': extract.content,
                    'context': extract.context,
                    'priority': extract.priority,
                    'position': extract.position,
                    'document_title': extract.document.title if extract.document else None,
                    'tags': [tag.name for tag in extract.tags],
                    'learning_items': []
                }
                
                # Add learning items if requested
                if include_learning_items:
                    for item in extract.learning_items:
                        item_data = {
                            'item_type': item.item_type,
                            'question': item.question,
                            'answer': item.answer,
                            'priority': item.priority
                        }
                        extract_data['learning_items'].append(item_data)
                
                export_data['extracts'].append(extract_data)
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(extracts)} extracts to {filepath}")
            return True
            
        except Exception as e:
            logger.exception(f"Error exporting extracts: {e}")
            return False
    
    def export_learning_items(self, item_ids: List[int], filepath: str) -> bool:
        """
        Export learning items to a file.
        
        Args:
            item_ids: List of learning item IDs to export
            filepath: Path to save the export file
            
        Returns:
            True if export successful, False otherwise
        """
        try:
            # Get learning items
            items = self.db_session.query(LearningItem).filter(LearningItem.id.in_(item_ids)).all()
            if not items:
                logger.error(f"No learning items found with IDs: {item_ids}")
                return False
            
            # Build export data
            export_data = {
                'version': '1.0',
                'export_date': datetime.utcnow().isoformat(),
                'learning_items': []
            }
            
            # Fill export data
            for item in items:
                item_data = {
                    'item_type': item.item_type,
                    'question': item.question,
                    'answer': item.answer,
                    'priority': item.priority,
                    'extract_content': item.extract.content if item.extract else None,
                    'document_title': item.extract.document.title if item.extract and item.extract.document else None
                }
                
                export_data['learning_items'].append(item_data)
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(items)} learning items to {filepath}")
            return True
            
        except Exception as e:
            logger.exception(f"Error exporting learning items: {e}")
            return False
    
    def export_deck(self, extract_ids: List[int], filepath: str) -> bool:
        """
        Export a complete deck of knowledge items in a portable format.
        
        Args:
            extract_ids: List of extract IDs to include in the deck
            filepath: Path to save the export file
            
        Returns:
            True if export successful, False otherwise
        """
        try:
            # Get extracts
            extracts = self.db_session.query(Extract).filter(Extract.id.in_(extract_ids)).all()
            if not extracts:
                logger.error(f"No extracts found with IDs: {extract_ids}")
                return False
            
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Create deck structure
                os.makedirs(os.path.join(temp_dir, "extracts"), exist_ok=True)
                os.makedirs(os.path.join(temp_dir, "media"), exist_ok=True)
                
                # Build deck data
                deck_data = {
                    'version': '1.0',
                    'export_date': datetime.utcnow().isoformat(),
                    'title': f"Incrementum Deck - {datetime.utcnow().strftime('%Y-%m-%d')}",
                    'extracts': [],
                    'tags': []
                }
                
                # Collect all tags
                all_tags = set()
                
                # Process extracts
                for extract in extracts:
                    extract_data = {
                        'id': extract.id,
                        'content': extract.content,
                        'context': extract.context,
                        'priority': extract.priority,
                        'tags': [tag.name for tag in extract.tags],
                        'learning_items': []
                    }
                    
                    # Add tags to collection
                    all_tags.update(extract_data['tags'])
                    
                    # Process learning items
                    for item in extract.learning_items:
                        item_data = {
                            'id': item.id,
                            'item_type': item.item_type,
                            'question': item.question,
                            'answer': item.answer,
                            'priority': item.priority,
                            'interval': item.interval,
                            'repetitions': item.repetitions,
                            'easiness': item.easiness,
                            'media_files': []  # Placeholder for future media support
                        }
                        
                        extract_data['learning_items'].append(item_data)
                    
                    # Add extract to deck
                    deck_data['extracts'].append(extract_data)
                
                # Add tags to deck
                deck_data['tags'] = list(all_tags)
                
                # Write deck metadata
                with open(os.path.join(temp_dir, "deck.json"), 'w', encoding='utf-8') as f:
                    json.dump(deck_data, f, indent=2, ensure_ascii=False)
                
                # Create ZIP archive
                with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # Add deck metadata
                    zipf.write(os.path.join(temp_dir, "deck.json"), "deck.json")
                    
                    # Add readme
                    readme_content = f"""# Incrementum Learning Deck
                    
This deck was exported from Incrementum on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}.

It contains:
- {len(extracts)} extracts
- {sum(len(extract.learning_items) for extract in extracts)} learning items
- {len(all_tags)} tags

To import this deck, use the "Import Deck" function in Incrementum.
"""
                    
                    readme_path = os.path.join(temp_dir, "README.md")
                    with open(readme_path, 'w', encoding='utf-8') as f:
                        f.write(readme_content)
                    
                    zipf.write(readme_path, "README.md")
                
                logger.info(f"Exported deck with {len(extracts)} extracts to {filepath}")
                return True
                
            finally:
                # Clean up temporary directory
                shutil.rmtree(temp_dir)
            
        except Exception as e:
            logger.exception(f"Error exporting deck: {e}")
            return False
    
    def import_extracts(self, filepath: str, target_document_id: Optional[int] = None) -> Tuple[int, int]:
        """
        Import extracts from a file.
        
        Args:
            filepath: Path to the import file
            target_document_id: Optional document ID to associate with imported extracts
            
        Returns:
            Tuple of (number of extracts imported, number of learning items imported)
        """
        try:
            # Read import file
            with open(filepath, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Validate format
            if 'version' not in import_data or 'extracts' not in import_data:
                logger.error(f"Invalid import file format: {filepath}")
                return (0, 0)
            
            # Get target document if specified
            target_document = None
            if target_document_id:
                target_document = self.db_session.query(Document).get(target_document_id)
                if not target_document:
                    logger.error(f"Target document not found: {target_document_id}")
                    return (0, 0)
            
            # Import extracts
            extract_count = 0
            item_count = 0
            
            for extract_data in import_data['extracts']:
                # Create extract
                extract = Extract(
                    content=extract_data['content'],
                    context=extract_data.get('context'),
                    priority=extract_data.get('priority', 50),
                    position=extract_data.get('position'),
                    document_id=target_document.id if target_document else None,
                    created_date=datetime.utcnow(),
                    processed=False
                )
                
                self.db_session.add(extract)
                self.db_session.flush()  # Get ID for learning items
                
                extract_count += 1
                
                # Process tags
                if 'tags' in extract_data:
                    for tag_name in extract_data['tags']:
                        # Get or create tag
                        tag = self.db_session.query(Tag).filter(Tag.name == tag_name).first()
                        if not tag:
                            tag = Tag(name=tag_name)
                            self.db_session.add(tag)
                            self.db_session.flush()
                        
                        extract.tags.append(tag)
                
                # Import learning items
                if 'learning_items' in extract_data:
                    for item_data in extract_data['learning_items']:
                        # Create learning item
                        item = LearningItem(
                            extract_id=extract.id,
                            item_type=item_data['item_type'],
                            question=item_data['question'],
                            answer=item_data['answer'],
                            priority=item_data.get('priority', extract.priority),
                            created_date=datetime.utcnow()
                        )
                        
                        self.db_session.add(item)
                        item_count += 1
            
            # Commit changes
            self.db_session.commit()
            
            logger.info(f"Imported {extract_count} extracts and {item_count} learning items from {filepath}")
            return (extract_count, item_count)
            
        except Exception as e:
            logger.exception(f"Error importing extracts: {e}")
            self.db_session.rollback()
            return (0, 0)
    
    def import_learning_items(self, filepath: str, target_extract_id: int) -> int:
        """
        Import learning items from a file.
        
        Args:
            filepath: Path to the import file
            target_extract_id: Extract ID to associate with imported items
            
        Returns:
            Number of learning items imported
        """
        try:
            # Verify target extract exists
            target_extract = self.db_session.query(Extract).get(target_extract_id)
            if not target_extract:
                logger.error(f"Target extract not found: {target_extract_id}")
                return 0
            
            # Read import file
            with open(filepath, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Validate format
            if 'version' not in import_data or 'learning_items' not in import_data:
                logger.error(f"Invalid import file format: {filepath}")
                return 0
            
            # Import learning items
            item_count = 0
            
            for item_data in import_data['learning_items']:
                # Create learning item
                item = LearningItem(
                    extract_id=target_extract_id,
                    item_type=item_data['item_type'],
                    question=item_data['question'],
                    answer=item_data['answer'],
                    priority=item_data.get('priority', target_extract.priority),
                    created_date=datetime.utcnow()
                )
                
                self.db_session.add(item)
                item_count += 1
            
            # Commit changes
            self.db_session.commit()
            
            # Mark extract as processed
            if item_count > 0:
                target_extract.processed = True
                self.db_session.commit()
            
            logger.info(f"Imported {item_count} learning items to extract {target_extract_id}")
            return item_count
            
        except Exception as e:
            logger.exception(f"Error importing learning items: {e}")
            self.db_session.rollback()
            return 0
    
    def import_deck(self, filepath: str) -> Tuple[int, int, int]:
        """
        Import a deck of knowledge items.
        
        Args:
            filepath: Path to the deck file
            
        Returns:
            Tuple of (number of extracts imported, number of learning items imported, number of tags imported)
        """
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            
            try:
                # Extract ZIP archive
                with zipfile.ZipFile(filepath, 'r') as zipf:
                    zipf.extractall(temp_dir)
                
                # Read deck metadata
                deck_path = os.path.join(temp_dir, "deck.json")
                if not os.path.exists(deck_path):
                    logger.error(f"Invalid deck file, missing deck.json: {filepath}")
                    return (0, 0, 0)
                
                with open(deck_path, 'r', encoding='utf-8') as f:
                    deck_data = json.load(f)
                
                # Validate format
                if 'version' not in deck_data or 'extracts' not in deck_data:
                    logger.error(f"Invalid deck file format: {filepath}")
                    return (0, 0, 0)
                
                # Import tags
                tag_count = 0
                tag_map = {}  # Map tag names to Tag objects
                
                for tag_name in deck_data.get('tags', []):
                    # Get or create tag
                    tag = self.db_session.query(Tag).filter(Tag.name == tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        self.db_session.add(tag)
                        self.db_session.flush()
                        tag_count += 1
                    
                    tag_map[tag_name] = tag
                
                # Import extracts and learning items
                extract_count = 0
                item_count = 0
                
                for extract_data in deck_data['extracts']:
                    # Create extract
                    extract = Extract(
                        content=extract_data['content'],
                        context=extract_data.get('context'),
                        priority=extract_data.get('priority', 50),
                        created_date=datetime.utcnow(),
                        processed=len(extract_data.get('learning_items', [])) > 0
                    )
                    
                    self.db_session.add(extract)
                    self.db_session.flush()  # Get ID for learning items
                    
                    extract_count += 1
                    
                    # Add tags to extract
                    for tag_name in extract_data.get('tags', []):
                        if tag_name in tag_map:
                            extract.tags.append(tag_map[tag_name])
                    
                    # Import learning items
                    for item_data in extract_data.get('learning_items', []):
                        # Create learning item
                        item = LearningItem(
                            extract_id=extract.id,
                            item_type=item_data['item_type'],
                            question=item_data['question'],
                            answer=item_data['answer'],
                            priority=item_data.get('priority', extract.priority),
                            interval=item_data.get('interval', 0),
                            repetitions=item_data.get('repetitions', 0),
                            easiness=item_data.get('easiness', 2.5),
                            created_date=datetime.utcnow()
                        )
                        
                        self.db_session.add(item)
                        item_count += 1
                
                # Commit changes
                self.db_session.commit()
                
                logger.info(f"Imported deck with {extract_count} extracts, {item_count} learning items, and {tag_count} tags")
                return (extract_count, item_count, tag_count)
                
            finally:
                # Clean up temporary directory
                shutil.rmtree(temp_dir)
            
        except Exception as e:
            logger.exception(f"Error importing deck: {e}")
            self.db_session.rollback()
            return (0, 0, 0)
    
    def export_all_data(self, filepath: str, format_type: str = "json") -> bool:
        """
        Export all data (extracts, learning items, documents, tags) to a single file.
        
        Args:
            filepath: Path to save the export file
            format_type: Format to use (json, markdown, or text)
            
        Returns:
            True if export successful, False otherwise
        """
        try:
            # Get all data from the database
            documents = self.db_session.query(Document).all()
            extracts = self.db_session.query(Extract).all()
            learning_items = self.db_session.query(LearningItem).all()
            tags = self.db_session.query(Tag).all()
            categories = self.db_session.query(Category).all()
            
            if format_type.lower() == "json":
                return self._export_all_json(filepath, documents, extracts, learning_items, tags, categories)
            elif format_type.lower() == "markdown":
                return self._export_all_markdown(filepath, documents, extracts, learning_items, tags, categories)
            elif format_type.lower() == "text":
                return self._export_all_text(filepath, documents, extracts, learning_items, tags, categories)
            else:
                logger.error(f"Unsupported export format: {format_type}")
                return False
                
        except Exception as e:
            logger.exception(f"Error exporting all data: {e}")
            return False
    
    def _export_all_json(self, filepath: str, documents, extracts, learning_items, tags, categories) -> bool:
        """Export all data in JSON format."""
        export_data = {
            'version': '1.0',
            'export_date': datetime.utcnow().isoformat(),
            'categories': [],
            'documents': [],
            'extracts': [],
            'learning_items': [],
            'tags': []
        }
        
        # Add categories
        for category in categories:
            cat_data = {
                'id': category.id,
                'name': category.name,
                'description': category.description,
                'parent_id': category.parent_id
            }
            export_data['categories'].append(cat_data)
        
        # Add documents
        for document in documents:
            doc_data = {
                'id': document.id,
                'title': document.title,
                'author': document.author,
                'content_type': document.content_type,
                'imported_date': document.imported_date.isoformat() if document.imported_date else None,
                'category_id': document.category_id,
                'tags': [tag.name for tag in document.tags]
            }
            export_data['documents'].append(doc_data)
        
        # Add extracts
        for extract in extracts:
            extract_data = {
                'id': extract.id,
                'content': extract.content,
                'context': extract.context,
                'document_id': extract.document_id,
                'position': extract.position,
                'priority': extract.priority,
                'created_date': extract.created_date.isoformat() if extract.created_date else None,
                'tags': [tag.name for tag in extract.tags]
            }
            export_data['extracts'].append(extract_data)
        
        # Add learning items
        for item in learning_items:
            item_data = {
                'id': item.id,
                'item_type': item.item_type,
                'question': item.question,
                'answer': item.answer,
                'extract_id': item.extract_id,
                'priority': item.priority,
                'next_review': item.next_review.isoformat() if item.next_review else None,
                'last_review': item.last_review.isoformat() if item.last_review else None,
                'interval': item.interval,
                'easiness': item.easiness,
                'repetitions': item.repetitions
            }
            export_data['learning_items'].append(item_data)
        
        # Add tags
        for tag in tags:
            tag_data = {
                'id': tag.id,
                'name': tag.name
            }
            export_data['tags'].append(tag_data)
        
        # Write to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported all data to {filepath} in JSON format")
        return True
    
    def _export_all_markdown(self, filepath: str, documents, extracts, learning_items, tags, categories) -> bool:
        """Export all data in Markdown format."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                # Header
                f.write(f"# Incrementum Export\n\n")
                f.write(f"*Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
                
                # Categories
                f.write(f"## Categories ({len(categories)})\n\n")
                for category in categories:
                    parent_info = f" (Child of: {category.parent.name})" if category.parent else ""
                    f.write(f"### {category.name}{parent_info}\n\n")
                    if category.description:
                        f.write(f"{category.description}\n\n")
                
                # Documents
                f.write(f"## Documents ({len(documents)})\n\n")
                for document in documents:
                    category_info = f" [Category: {document.category.name}]" if document.category else ""
                    f.write(f"### {document.title}{category_info}\n\n")
                    
                    if document.author:
                        f.write(f"**Author:** {document.author}  \n")
                    
                    f.write(f"**Type:** {document.content_type}  \n")
                    f.write(f"**Imported:** {document.imported_date.strftime('%Y-%m-%d') if document.imported_date else 'Unknown'}  \n")
                    
                    if document.tags:
                        f.write(f"**Tags:** {', '.join([tag.name for tag in document.tags])}  \n")
                    
                    f.write("\n")
                
                # Extracts
                f.write(f"## Extracts ({len(extracts)})\n\n")
                for extract in extracts:
                    doc_title = extract.document.title if extract.document else "Unknown Document"
                    f.write(f"### Extract from {doc_title}\n\n")
                    
                    f.write(f"**Content:**\n\n")
                    f.write(f"```\n{extract.content}\n```\n\n")
                    
                    if extract.context:
                        f.write(f"**Context:**\n\n")
                        f.write(f"```\n{extract.context}\n```\n\n")
                    
                    if extract.tags:
                        f.write(f"**Tags:** {', '.join([tag.name for tag in extract.tags])}\n\n")
                    
                    f.write(f"**Created:** {extract.created_date.strftime('%Y-%m-%d') if extract.created_date else 'Unknown'}\n\n")
                    f.write(f"**Priority:** {extract.priority}\n\n")
                
                # Learning Items
                f.write(f"## Learning Items ({len(learning_items)})\n\n")
                for item in learning_items:
                    item_extract = "Unknown Extract" 
                    if item.extract:
                        item_extract = f"{item.extract.content[:50]}..." if len(item.extract.content) > 50 else item.extract.content
                    
                    f.write(f"### {item.item_type} Item\n\n")
                    f.write(f"**Question:**\n\n{item.question}\n\n")
                    f.write(f"**Answer:**\n\n{item.answer}\n\n")
                    f.write(f"**Extract:** {item_extract}\n\n")
                    f.write(f"**Next Review:** {item.next_review.strftime('%Y-%m-%d') if item.next_review else 'Not scheduled'}\n\n")
                    f.write(f"**Last Review:** {item.last_review.strftime('%Y-%m-%d') if item.last_review else 'Never reviewed'}\n\n")
                    f.write(f"**Repetitions:** {item.repetitions}\n\n")
                    f.write(f"**Interval:** {item.interval} days\n\n")
                    f.write(f"**Easiness:** {item.easiness}\n\n")
                
                # Tags
                f.write(f"## Tags ({len(tags)})\n\n")
                tag_list = sorted([tag.name for tag in tags])
                for i, tag_name in enumerate(tag_list):
                    f.write(f"`{tag_name}` ")
                    if (i + 1) % 5 == 0:
                        f.write("\n")
            
            logger.info(f"Exported all data to {filepath} in Markdown format")
            return True
            
        except Exception as e:
            logger.exception(f"Error exporting to Markdown: {e}")
            return False
    
    def _export_all_text(self, filepath: str, documents, extracts, learning_items, tags, categories) -> bool:
        """Export all data in plain text format."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                # Header
                f.write(f"INCREMENTUM EXPORT\n")
                f.write(f"=================\n\n")
                f.write(f"Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # Categories
                f.write(f"CATEGORIES ({len(categories)})\n")
                f.write(f"=========================\n\n")
                for category in categories:
                    parent_info = f" (Child of: {category.parent.name})" if category.parent else ""
                    f.write(f"{category.name}{parent_info}\n")
                    if category.description:
                        f.write(f"  {category.description}\n")
                    f.write("\n")
                
                # Documents
                f.write(f"DOCUMENTS ({len(documents)})\n")
                f.write(f"=======================\n\n")
                for document in documents:
                    category_info = f" [Category: {document.category.name}]" if document.category else ""
                    f.write(f"{document.title}{category_info}\n")
                    
                    if document.author:
                        f.write(f"  Author: {document.author}\n")
                    
                    f.write(f"  Type: {document.content_type}\n")
                    f.write(f"  Imported: {document.imported_date.strftime('%Y-%m-%d') if document.imported_date else 'Unknown'}\n")
                    
                    if document.tags:
                        f.write(f"  Tags: {', '.join([tag.name for tag in document.tags])}\n")
                    
                    f.write("\n")
                
                # Extracts
                f.write(f"EXTRACTS ({len(extracts)})\n")
                f.write(f"====================\n\n")
                for extract in extracts:
                    doc_title = extract.document.title if extract.document else "Unknown Document"
                    f.write(f"Extract from {doc_title}\n")
                    f.write(f"-------------------------\n")
                    
                    f.write(f"Content:\n{extract.content}\n\n")
                    
                    if extract.context:
                        f.write(f"Context:\n{extract.context}\n\n")
                    
                    if extract.tags:
                        f.write(f"Tags: {', '.join([tag.name for tag in extract.tags])}\n")
                    
                    f.write(f"Created: {extract.created_date.strftime('%Y-%m-%d') if extract.created_date else 'Unknown'}\n")
                    f.write(f"Priority: {extract.priority}\n\n")
                
                # Learning Items
                f.write(f"LEARNING ITEMS ({len(learning_items)})\n")
                f.write(f"=============================\n\n")
                for item in learning_items:
                    item_extract = "Unknown Extract" 
                    if item.extract:
                        item_extract = f"{item.extract.content[:50]}..." if len(item.extract.content) > 50 else item.extract.content
                    
                    f.write(f"{item.item_type} Item\n")
                    f.write(f"-------------------------\n")
                    f.write(f"Question:\n{item.question}\n\n")
                    f.write(f"Answer:\n{item.answer}\n\n")
                    f.write(f"Extract: {item_extract}\n")
                    f.write(f"Next Review: {item.next_review.strftime('%Y-%m-%d') if item.next_review else 'Not scheduled'}\n")
                    f.write(f"Last Review: {item.last_review.strftime('%Y-%m-%d') if item.last_review else 'Never reviewed'}\n")
                    f.write(f"Repetitions: {item.repetitions}\n")
                    f.write(f"Interval: {item.interval} days\n")
                    f.write(f"Easiness: {item.easiness}\n\n")
                
                # Tags
                f.write(f"TAGS ({len(tags)})\n")
                f.write(f"=============\n\n")
                for tag in tags:
                    f.write(f"{tag.name}\n")
            
            logger.info(f"Exported all data to {filepath} in Text format")
            return True
            
        except Exception as e:
            logger.exception(f"Error exporting to Text: {e}")
            return False


# ui/export_dialog.py

import os
import logging
from typing import List, Dict, Any, Optional, Set

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QListWidget, QListWidgetItem, 
    QCheckBox, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QGroupBox,
    QFormLayout, QLineEdit, QTextEdit
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, pyqtSlot

from core.knowledge_base.models import Extract, LearningItem
from core.knowledge_base.export_manager import ExportManager

logger = logging.getLogger(__name__)

class ExportDialog(QDialog):
    """Dialog for exporting knowledge items."""
    
    def __init__(self, db_session, extract_ids=None, item_ids=None, parent=None):
        super().__init__(parent)
        
        self.db_session = db_session
        self.export_manager = ExportManager(db_session)
        self.extract_ids = extract_ids or []
        self.item_ids = item_ids or []
        
        # Create UI
        self._create_ui()
        
        # Load items
        self._load_items()
    
    def _create_ui(self):
        """Create the UI layout."""
        self.setWindowTitle("Export Knowledge Items")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        main_layout = QVBoxLayout(self)
        
        # Content to export
        content_group = QGroupBox("Content to Export")
        content_layout = QVBoxLayout(content_group)
        
        # Export type selection
        type_layout = QHBoxLayout()
        
        self.type_group = QButtonGroup(self)
        
        self.extracts_radio = QRadioButton("Extracts")
        self.extracts_radio.setChecked(True)
        self.type_group.addButton(self.extracts_radio)
        type_layout.addWidget(self.extracts_radio)
        
        self.items_radio = QRadioButton("Learning Items")
        self.type_group.addButton(self.items_radio)
        type_layout.addWidget(self.items_radio)
        
        self.deck_radio = QRadioButton("Complete Deck")
        self.type_group.addButton(self.deck_radio)
        type_layout.addWidget(self.deck_radio)
        
        # Connect signals
        self.extracts_radio.toggled.connect(self._on_export_type_changed)
        self.items_radio.toggled.connect(self._on_export_type_changed)
        self.deck_radio.toggled.connect(self._on_export_type_changed)
        
        content_layout.addLayout(type_layout)
        
        # Include learning items checkbox (for extracts)
        self.include_items_check = QCheckBox("Include linked learning items")
        self.include_items_check.setChecked(True)
        content_layout.addWidget(self.include_items_check)
        
        # Deck title (for deck export)
        deck_title_layout = QFormLayout()
        self.deck_title = QLineEdit()
        self.deck_title.setText(f"Incrementum Deck - {extract_ids or item_ids}")
        deck_title_layout.addRow("Deck Title:", self.deck_title)
        content_layout.addLayout(deck_title_layout)
        
        # Deck description (for deck export)
        deck_desc_layout = QFormLayout()
        self.deck_description = QTextEdit()
        self.deck_description.setMaximumHeight(100)
        self.deck_description.setText("Exported from Incrementum")
        deck_desc_layout.addRow("Description:", self.deck_description)
        content_layout.addLayout(deck_desc_layout)
        
        # Items list
        self.items_list = QListWidget()
        self.items_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        content_layout.addWidget(self.items_list)
        
        main_layout.addWidget(content_group)
        
        # Export options
        options_group = QGroupBox("Export Options")
        options_layout = QFormLayout(options_group)
        
        # Format selection
        self.format_combo = QComboBox()
        self.format_combo.addItem("JSON Format (.json)", "json")
        self.format_combo.addItem("Deck Package (.izd)", "izd")
        options_layout.addRow("Export Format:", self.format_combo)
        
        # Connect signals
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        
        main_layout.addWidget(options_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.export_button = QPushButton("Export...")
        self.export_button.clicked.connect(self._on_export)
        button_layout.addWidget(self.export_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # Initial UI state
        self._on_export_type_changed()
        self._on_format_changed()
    
    def _load_items(self):
        """Load items based on selection type."""
        self.items_list.clear()
        
        if self.extracts_radio.isChecked():
            # Load extracts
            if self.extract_ids:
                extracts = self.db_session.query(Extract).filter(Extract.id.in_(self.extract_ids)).all()
                
                for extract in extracts:
                    # Create list item with shortened content
                    content = extract.content
                    if len(content) > 100:
                        content = content[:97] + "..."
                    
                    item = QListWidgetItem(content)
                    item.setData(Qt.ItemDataRole.UserRole, extract.id)
                    item.setSelected(True)  # Select by default
                    self.items_list.addItem(item)
            else:
                # No extracts specified, show message
                self.items_list.addItem("No extracts selected")
        
        elif self.items_radio.isChecked():
            # Load learning items
            if self.item_ids:
                items = self.db_session.query(LearningItem).filter(LearningItem.id.in_(self.item_ids)).all()
                
                for item in items:
                    # Create list item with question
                    question = item.question
                    if len(question) > 100:
                        question = question[:97] + "..."
                    
                    list_item = QListWidgetItem(question)
                    list_item.setData(Qt.ItemDataRole.UserRole, item.id)
                    list_item.setSelected(True)  # Select by default
                    self.items_list.addItem(list_item)
            else:
                # No items specified, try to load items from extracts
                if self.extract_ids:
                    items = self.db_session.query(LearningItem).filter(
                        LearningItem.extract_id.in_(self.extract_ids)
                    ).all()
                    
                    for item in items:
                        # Create list item with question
                        question = item.question
                        if len(question) > 100:
                            question = question[:97] + "..."
                        
                        list_item = QListWidgetItem(question)
                        list_item.setData(Qt.ItemDataRole.UserRole, item.id)
                        list_item.setSelected(True)  # Select by default
                        self.items_list.addItem(list_item)
                else:
                    # No items or extracts specified, show message
                    self.items_list.addItem("No learning items selected")
        
        elif self.deck_radio.isChecked():
            # For deck export, we use extracts as the base
            if self.extract_ids:
                extracts = self.db_session.query(Extract).filter(Extract.id.in_(self.extract_ids)).all()
                
                for extract in extracts:
                    # Create list item with shortened content
                    content = extract.content
                    if len(content) > 100:
                        content = content[:97] + "..."
                    
                    item = QListWidgetItem(content)
                    item.setData(Qt.ItemDataRole.UserRole, extract.id)
                    item.setSelected(True)  # Select by default
                    self.items_list.addItem(item)
            else:
                # No extracts specified, show message
                self.items_list.addItem("No extracts selected for deck export")
    
    @pyqtSlot()
    def _on_export_type_changed(self):
        """Handle export type selection change."""
        # Update UI based on selection
        if self.extracts_radio.isChecked():
            self.include_items_check.setVisible(True)
            self.deck_title.setVisible(False)
            self.deck_description.setVisible(False)
            self.format_combo.setEnabled(True)
        elif self.items_radio.isChecked():
            self.include_items_check.setVisible(False)
            self.deck_title.setVisible(False)
            self.deck_description.setVisible(False)
            self.format_combo.setEnabled(True)
        elif self.deck_radio.isChecked():
            self.include_items_check.setVisible(False)
            self.deck_title.setVisible(True)
            self.deck_description.setVisible(True)
            # Force package format for deck
            self.format_combo.setCurrentIndex(1)  # Deck Package
            self.format_combo.setEnabled(False)
        
        # Reload items
        self._load_items()
    
    @pyqtSlot()
    def _on_format_changed(self):
        """Handle format selection change."""
        # Adjust UI based on selected format
        format_type = self.format_combo.currentData()
        
        if format_type == "izd":
            # Package format forces deck export
            self.deck_radio.setChecked(True)
            self.format_combo.setEnabled(False)
        else:
            # JSON format allows any export type
            self.format_combo.setEnabled(True)
    
    @pyqtSlot()
    def _on_export(self):
        """Handle export button click."""
        # Get selected IDs
        selected_ids = []
        for i in range(self.items_list.count()):
            item = self.items_list.item(i)
            if item.isSelected():
                item_id = item.data(Qt.ItemDataRole.UserRole)
                if item_id is not None:
                    selected_ids.append(item_id)
        
        if not selected_ids:
            QMessageBox.warning(
                self, "No Items Selected", 
                "Please select at least one item to export."
            )
            return
        
        # Get export format
        format_type = self.format_combo.currentData()
        
        # Get file extension
        if format_type == "json":
            file_ext = ".json"
            file_filter = "JSON Files (*.json)"
        else:  # izd
            file_ext = ".izd"
            file_filter = "Incrementum Deck Files (*.izd)"
        
        # Get save path
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export To", "", file_filter
        )
        
        if not filepath:
            return
        
        # Add extension if missing
        if not filepath.endswith(file_ext):
            filepath += file_ext
        
        # Perform export based on type
        success = False
        
        if self.extracts_radio.isChecked():
            # Export extracts
            include_items = self.include_items_check.isChecked()
            success = self.export_manager.export_extracts(selected_ids, filepath, include_items)
            
            if success:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"Successfully exported {len(selected_ids)} extracts to {filepath}"
                )
        
        elif self.items_radio.isChecked():
            # Export learning items
            success = self.export_manager.export_learning_items(selected_ids, filepath)
            
            if success:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"Successfully exported {len(selected_ids)} learning items to {filepath}"
                )
        
        elif self.deck_radio.isChecked():
            # Export deck
            success = self.export_manager.export_deck(selected_ids, filepath)
            
            if success:
                QMessageBox.information(
                    self, "Export Successful", 
                    f"Successfully exported deck with {len(selected_ids)} extracts to {filepath}"
                )
        
        if success:
            self.accept()
        else:
            QMessageBox.warning(
                self, "Export Failed", 
                f"Failed to export to {filepath}"
            )


# ui/import_dialog.py

import os
import logging
from typing import List, Dict, Any, Optional, Set

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QRadioButton, QButtonGroup,
    QFileDialog, QMessageBox, QGroupBox,
    QFormLayout, QComboBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, pyqtSlot

from core.knowledge_base.models import Document, Extract
from core.knowledge_base.export_manager import ExportManager

logger = logging.getLogger(__name__)

class ImportDialog(QDialog):
    """Dialog for importing knowledge items."""
    
    importCompleted = pyqtSignal(int, int, int)  # extracts, items, tags
    
    def __init__(self, db_session, parent=None):
        super().__init__(parent)
        
        self.db_session = db_session
        self.export_manager = ExportManager(db_session)
        
        # Create UI
        self._create_ui()
    
    def _create_ui(self):
        """Create the UI layout."""
        self.setWindowTitle("Import Knowledge Items")
        self.setMinimumWidth(500)
        
        main_layout = QVBoxLayout(self)
        
        # Import type selection
        type_group = QGroupBox("Import Type")
        type_layout = QVBoxLayout(type_group)
        
        self.type_group = QButtonGroup(self)
        
        self.extracts_radio = QRadioButton("Extracts")
        self.extracts_radio.setChecked(True)
        self.type_group.addButton(self.extracts_radio)
        type_layout.addWidget(self.extracts_radio)
        
        self.items_radio = QRadioButton("Learning Items")
        self.type_group.addButton(self.items_radio)
        type_layout.addWidget(self.items_radio)
        
        self.deck_radio = QRadioButton("Complete Deck")
        self.type_group.addButton(self.deck_radio)
        type_layout.addWidget(self.deck_radio)
        
        main_layout.addWidget(type_group)
        
        # Import options
        options_group = QGroupBox("Import Options")
        options_layout = QFormLayout(options_group)
        
        # Source document selection (for extracts)
        self.document_combo = QComboBox()
        self.document_combo.addItem("None - Standalone Extracts", None)
        
        # Populate documents
        documents = self.db_session.query(Document).order_by(Document.title).all()
        for doc in documents:
            self.document_combo.addItem(doc.title, doc.id)
        
        options_layout.addRow("Target Document:", self.document_combo)
        
        # Target extract selection (for learning items)
        self.extract_combo = QComboBox()
        self.extract_combo.setEnabled(False)  # Initially disabled
        
        options_layout.addRow("Target Extract:", self.extract_combo)
        
        main_layout.addWidget(options_group)
        
        # File selection
        file_group = QGroupBox("File")
        file_layout = QHBoxLayout(file_group)
        
        self.file_path = QLabel("No file selected")
        file_layout.addWidget(self.file_path)
        
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._on_browse)
        file_layout.addWidget(self.browse_button)
        
        main_layout.addWidget(file_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self._on_import)
        self.import_button.setEnabled(False)  # Initially disabled
        button_layout.addWidget(self.import_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # Connect signals
        self.extracts_radio.toggled.connect(self._update_ui)
        self.items_radio.toggled.connect(self._update_ui)
        self.deck_radio.toggled.connect(self._update_ui)
        self.items_radio.toggled.connect(self._populate_extracts)
        
        # Initial UI update
        self._update_ui()
    
    def _update_ui(self):
        """Update UI based on import type."""
        # Document combo is only relevant for extracts import
        document_enabled = self.extracts_radio.isChecked()
        self.document_combo.setEnabled(document_enabled)
        
        # Extract combo is only relevant for learning items import
        extract_enabled = self.items_radio.isChecked()
        self.extract_combo.setEnabled(extract_enabled)
    
    def _populate_extracts(self):
        """Populate the extract combo box."""
        self.extract_combo.clear()
        
        if not self.items_radio.isChecked():
            return
        
        # Query extracts
        extracts = self.db_session.query(Extract).order_by(Extract.created_date.desc()).limit(50).all()
        
        for extract in extracts:
            # Create display text from extract content
            content = extract.content
            if len(content) > 50:
                content = content[:47] + "..."
            
            self.extract_combo.addItem(content, extract.id)
    
    @pyqtSlot()
    def _on_browse(self):
        """Handle browse button click."""
        # Determine file filter based on import type
        if self.deck_radio.isChecked():
            file_filter = "Incrementum Deck Files (*.izd)"
        else:
            file_filter = "JSON Files (*.json);;Incrementum Deck Files (*.izd)"
        
        # Get file path
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Select File to Import", "", file_filter
        )
        
        if filepath:
            self.file_path.setText(filepath)
            self.import_button.setEnabled(True)
            
            # If it's a deck file, force deck import
            if filepath.lower().endswith('.izd'):
                self.deck_radio.setChecked(True)
    
    @pyqtSlot()
    def _on_import(self):
        """Handle import button click."""
        filepath = self.file_path.text()
        if filepath == "No file selected" or not os.path.exists(filepath):
            QMessageBox.warning(
                self, "Invalid File", 
                "Please select a valid file to import."
            )
            return
        
        # Perform import based on type
        if self.extracts_radio.isChecked():
            # Import extracts
            target_document_id = self.document_combo.currentData()
            extracts_count, items_count = self.export_manager.import_extracts(filepath, target_document_id)
            
            if extracts_count > 0:
                QMessageBox.information(
                    self, "Import Successful", 
                    f"Successfully imported {extracts_count} extracts and {items_count} learning items."
                )
                self.importCompleted.emit(extracts_count, items_count, 0)
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Import Failed", 
                    "Failed to import extracts from the file."
                )
        
        elif self.items_radio.isChecked():
            # Import learning items
            target_extract_id = self.extract_combo.currentData()
            if not target_extract_id:
                QMessageBox.warning(
                    self, "No Target Extract", 
                    "Please select a target extract for the learning items."
                )
                return
            
            items_count = self.export_manager.import_learning_items(filepath, target_extract_id)
            
            if items_count > 0:
                QMessageBox.information(
                    self, "Import Successful", 
                    f"Successfully imported {items_count} learning items."
                )
                self.importCompleted.emit(0, items_count, 0)
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Import Failed", 
                    "Failed to import learning items from the file."
                )
        
        elif self.deck_radio.isChecked():
            # Import deck
            extracts_count, items_count, tags_count = self.export_manager.import_deck(filepath)
            
            if extracts_count > 0 or items_count > 0:
                QMessageBox.information(
                    self, "Import Successful", 
                    f"Successfully imported deck with {extracts_count} extracts, "
                    f"{items_count} learning items, and {tags_count} tags."
                )
                self.importCompleted.emit(extracts_count, items_count, tags_count)
                self.accept()
            else:
                QMessageBox.warning(
                    self, "Import Failed", 
                    "Failed to import deck from the file."
                )
