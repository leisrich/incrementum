# core/knowledge_base/backup_manager.py

import os
import logging
import tempfile
import json
import shutil
import zipfile
import datetime
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from appdirs import user_data_dir

from core.knowledge_base.models import Base, Document, Category, Extract, LearningItem, Tag, ReviewLog

logger = logging.getLogger(__name__)

class BackupManager:
    """
    Manager for database backups and restoration.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        
        # Get application data directory
        self.data_dir = user_data_dir("Incrementum", "Incrementum")
        self.backup_dir = os.path.join(self.data_dir, "backups")
        
        # Create backup directory if it doesn't exist
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_backup(self, include_files: bool = True) -> Optional[str]:
        """
        Create a backup of the database and optionally document files.
        
        Args:
            include_files: Whether to include document files in the backup
            
        Returns:
            Path to the backup file, or None if backup failed
        """
        try:
            # Create a temporary directory for the backup
            temp_dir = tempfile.mkdtemp()
            
            # Export database to JSON
            database_path = os.path.join(temp_dir, "database.json")
            if not self._export_database_to_json(database_path):
                return None
            
            # If requested, copy document files
            if include_files:
                files_dir = os.path.join(temp_dir, "files")
                os.makedirs(files_dir, exist_ok=True)
                
                if not self._backup_document_files(files_dir):
                    return None
            
            # Create a zip file with the backup
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"incrementum_backup_{timestamp}.zip"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add database JSON
                zipf.write(database_path, os.path.basename(database_path))
                
                # Add document files if included
                if include_files:
                    for root, _, files in os.walk(files_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            zipf.write(
                                file_path, 
                                os.path.relpath(file_path, temp_dir)
                            )
            
            # Cleanup temporary directory
            shutil.rmtree(temp_dir)
            
            logger.info(f"Backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.exception(f"Error creating backup: {e}")
            return None
    
    def restore_backup(self, backup_path: str) -> bool:
        """
        Restore a backup.
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            True if restoration successful, False otherwise
        """
        try:
            # Create a temporary directory for restoring
            temp_dir = tempfile.mkdtemp()
            
            # Extract backup
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            # Check if database JSON exists
            database_path = os.path.join(temp_dir, "database.json")
            if not os.path.exists(database_path):
                logger.error(f"Database file not found in backup: {backup_path}")
                return False
            
            # Restore database
            if not self._import_database_from_json(database_path):
                return False
            
            # Check if document files exist
            files_dir = os.path.join(temp_dir, "files")
            if os.path.exists(files_dir):
                if not self._restore_document_files(files_dir):
                    return False
            
            # Cleanup temporary directory
            shutil.rmtree(temp_dir)
            
            logger.info(f"Backup restored: {backup_path}")
            return True
            
        except Exception as e:
            logger.exception(f"Error restoring backup: {e}")
            return False
    
    def get_backup_list(self) -> List[Dict[str, Any]]:
        """
        Get a list of available backups.
        
        Returns:
            List of dictionaries with backup information
        """
        backups = []
        
        try:
            # List backup files
            for filename in os.listdir(self.backup_dir):
                if filename.endswith(".zip") and filename.startswith("incrementum_backup_"):
                    backup_path = os.path.join(self.backup_dir, filename)
                    
                    # Get file info
                    file_stat = os.stat(backup_path)
                    
                    # Extract timestamp from filename
                    timestamp_str = filename.replace("incrementum_backup_", "").replace(".zip", "")
                    timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                    
                    # Check if it includes files
                    has_files = False
                    with zipfile.ZipFile(backup_path, 'r') as zipf:
                        file_list = zipf.namelist()
                        has_files = any(name.startswith("files/") for name in file_list)
                    
                    backups.append({
                        'filename': filename,
                        'path': backup_path,
                        'timestamp': timestamp,
                        'size': file_stat.st_size,
                        'has_files': has_files
                    })
            
            # Sort by timestamp (newest first)
            backups.sort(key=lambda x: x['timestamp'], reverse=True)
            
        except Exception as e:
            logger.exception(f"Error listing backups: {e}")
        
        return backups
    
    def delete_backup(self, backup_path: str) -> bool:
        """
        Delete a backup file.
        
        Args:
            backup_path: Path to the backup file
            
        Returns:
            True if deletion successful, False otherwise
        """
        try:
            if os.path.exists(backup_path):
                os.remove(backup_path)
                logger.info(f"Backup deleted: {backup_path}")
                return True
            else:
                logger.error(f"Backup not found: {backup_path}")
                return False
        except Exception as e:
            logger.exception(f"Error deleting backup: {e}")
            return False
    
    def _export_database_to_json(self, output_path: str) -> bool:
        """
        Export database to JSON.
        
        Args:
            output_path: Path to save the JSON file
            
        Returns:
            True if export successful, False otherwise
        """
        try:
            # Get database tables
            tables = {
                'categories': Category,
                'documents': Document,
                'extracts': Extract,
                'learning_items': LearningItem,
                'tags': Tag,
                'review_logs': ReviewLog
            }
            
            # Export data from each table
            data = {}
            
            for table_name, model_class in tables.items():
                # Get all records
                records = self.db_session.query(model_class).all()
                
                # Convert to dictionaries
                table_data = []
                for record in records:
                    record_dict = {}
                    
                    # Get columns
                    for column in inspect(model_class).columns:
                        column_name = column.name
                        value = getattr(record, column_name)
                        
                        # Convert non-serializable types
                        if isinstance(value, datetime.datetime):
                            value = value.isoformat()
                        
                        record_dict[column_name] = value
                    
                    table_data.append(record_dict)
                
                data[table_name] = table_data
            
            # Export many-to-many relationships
            data['relationships'] = self._export_relationships()
            
            # Write to file
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            return True
            
        except Exception as e:
            logger.exception(f"Error exporting database: {e}")
            return False
    
    def _export_relationships(self) -> Dict[str, List[Dict[str, int]]]:
        """
        Export many-to-many relationships.
        
        Returns:
            Dictionary mapping relationship names to lists of relationship dictionaries
        """
        relationships = {}
        
        try:
            # Document tags
            document_tags = []
            
            doc_tag_pairs = self.db_session.query(
                Document.id, Tag.id
            ).filter(
                Document.tags.any()
            ).join(
                Document.tags
            ).all()
            
            for doc_id, tag_id in doc_tag_pairs:
                document_tags.append({
                    'document_id': doc_id,
                    'tag_id': tag_id
                })
            
            relationships['document_tags'] = document_tags
            
            # Extract tags
            extract_tags = []
            
            extract_tag_pairs = self.db_session.query(
                Extract.id, Tag.id
            ).filter(
                Extract.tags.any()
            ).join(
                Extract.tags
            ).all()
            
            for extract_id, tag_id in extract_tag_pairs:
                extract_tags.append({
                    'extract_id': extract_id,
                    'tag_id': tag_id
                })
            
            relationships['extract_tags'] = extract_tags
            
        except Exception as e:
            logger.exception(f"Error exporting relationships: {e}")
        
        return relationships
    
    def _import_database_from_json(self, input_path: str) -> bool:
        """
        Import database from JSON.
        
        Args:
            input_path: Path to the JSON file
            
        Returns:
            True if import successful, False otherwise
        """
        try:
            # Read JSON data
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Create a new database connection
            db_path = os.path.join(self.data_dir, "incrementum.db")
            backup_db_path = os.path.join(self.data_dir, "incrementum_pre_restore.db")
            
            # Backup existing database
            if os.path.exists(db_path):
                shutil.copy(db_path, backup_db_path)
            
            # Create new database
            engine = create_engine(f"sqlite:///{db_path}")
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
            
            # Create a new session
            Session = Session.configure(bind=engine)
            new_session = Session()
            
            # Import data for each table
            self._import_categories(new_session, data.get('categories', []))
            self._import_documents(new_session, data.get('documents', []))
            self._import_tags(new_session, data.get('tags', []))
            self._import_extracts(new_session, data.get('extracts', []))
            self._import_learning_items(new_session, data.get('learning_items', []))
            self._import_review_logs(new_session, data.get('review_logs', []))
            
            # Import relationships
            self._import_relationships(new_session, data.get('relationships', {}))
            
            # Commit all changes
            new_session.commit()
            new_session.close()
            
            # Reconnect the main session
            self.db_session.close()
            self.db_session = Session()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error importing database: {e}")
            
            # Try to restore the backup
            try:
                db_path = os.path.join(self.data_dir, "incrementum.db")
                backup_db_path = os.path.join(self.data_dir, "incrementum_pre_restore.db")
                
                if os.path.exists(backup_db_path):
                    shutil.copy(backup_db_path, db_path)
                    logger.info("Restored database from pre-restore backup")
            except Exception as restore_error:
                logger.exception(f"Error restoring database backup: {restore_error}")
            
            return False
    
    def _import_categories(self, session: Session, categories_data: List[Dict[str, Any]]) -> None:
        """Import categories from JSON data."""
        # First pass: create all categories without parent relationships
        id_map = {}
        
        for category_data in categories_data:
            category = Category(
                name=category_data['name'],
                description=category_data.get('description')
            )
            session.add(category)
            session.flush()
            
            # Save mapping from old ID to new ID
            id_map[category_data['id']] = category.id
        
        # Second pass: set parent relationships
        for category_data in categories_data:
            if category_data.get('parent_id'):
                old_id = category_data['id']
                old_parent_id = category_data['parent_id']
                
                # Get mapped IDs
                new_id = id_map.get(old_id)
                new_parent_id = id_map.get(old_parent_id)
                
                if new_id and new_parent_id:
                    category = session.query(Category).get(new_id)
                    category.parent_id = new_parent_id
    
    def _import_documents(self, session: Session, documents_data: List[Dict[str, Any]]) -> None:
        """Import documents from JSON data."""
        for document_data in documents_data:
            document = Document(
                title=document_data['title'],
                author=document_data.get('author', ''),
                source_url=document_data.get('source_url', ''),
                file_path=document_data['file_path'],
                content_type=document_data['content_type'],
                processing_progress=document_data.get('processing_progress', 0.0),
                category_id=document_data.get('category_id')
            )
            
            # Parse dates
            if document_data.get('imported_date'):
                document.imported_date = datetime.datetime.fromisoformat(document_data['imported_date'])
            
            if document_data.get('last_accessed'):
                document.last_accessed = datetime.datetime.fromisoformat(document_data['last_accessed'])
            
            session.add(document)
            session.flush()
    
    def _import_tags(self, session: Session, tags_data: List[Dict[str, Any]]) -> None:
        """Import tags from JSON data."""
        for tag_data in tags_data:
            tag = Tag(
                name=tag_data['name']
            )
            session.add(tag)
            session.flush()
    
    def _import_extracts(self, session: Session, extracts_data: List[Dict[str, Any]]) -> None:
        """Import extracts from JSON data."""
        for extract_data in extracts_data:
            extract = Extract(
                content=extract_data['content'],
                context=extract_data.get('context'),
                document_id=extract_data['document_id'],
                parent_id=extract_data.get('parent_id'),
                position=extract_data.get('position'),
                priority=extract_data.get('priority', 50),
                processed=extract_data.get('processed', False)
            )
            
            # Parse dates
            if extract_data.get('created_date'):
                extract.created_date = datetime.datetime.fromisoformat(extract_data['created_date'])
            
            if extract_data.get('last_reviewed'):
                extract.last_reviewed = datetime.datetime.fromisoformat(extract_data['last_reviewed'])
            
            session.add(extract)
            session.flush()
    
    def _import_learning_items(self, session: Session, items_data: List[Dict[str, Any]]) -> None:
        """Import learning items from JSON data."""
        for item_data in items_data:
            item = LearningItem(
                extract_id=item_data['extract_id'],
                item_type=item_data['item_type'],
                question=item_data['question'],
                answer=item_data['answer'],
                interval=item_data.get('interval', 0),
                repetitions=item_data.get('repetitions', 0),
                easiness=item_data.get('easiness', 2.5),
                priority=item_data.get('priority', 50),
                difficulty=item_data.get('difficulty', 0.0)
            )
            
            # Parse dates
            if item_data.get('created_date'):
                item.created_date = datetime.datetime.fromisoformat(item_data['created_date'])
            
            if item_data.get('last_reviewed'):
                item.last_reviewed = datetime.datetime.fromisoformat(item_data['last_reviewed'])
            
            if item_data.get('next_review'):
                item.next_review = datetime.datetime.fromisoformat(item_data['next_review'])
            
            session.add(item)
            session.flush()
    
    def _import_review_logs(self, session: Session, logs_data: List[Dict[str, Any]]) -> None:
        """Import review logs from JSON data."""
        for log_data in logs_data:
            log = ReviewLog(
                learning_item_id=log_data['learning_item_id'],
                grade=log_data['grade'],
                response_time=log_data.get('response_time'),
                scheduled_interval=log_data.get('scheduled_interval'),
                actual_interval=log_data.get('actual_interval')
            )
            
            # Parse dates
            if log_data.get('review_date'):
                log.review_date = datetime.datetime.fromisoformat(log_data['review_date'])
            
            session.add(log)
            session.flush()
    
    def _import_relationships(self, session: Session, relationships_data: Dict[str, List[Dict[str, int]]]) -> None:
        """Import relationships from JSON data."""
        # Import document tags
        for rel in relationships_data.get('document_tags', []):
            document = session.query(Document).get(rel['document_id'])
            tag = session.query(Tag).get(rel['tag_id'])
            
            if document and tag:
                document.tags.append(tag)
        
        # Import extract tags
        for rel in relationships_data.get('extract_tags', []):
            extract = session.query(Extract).get(rel['extract_id'])
            tag = session.query(Tag).get(rel['tag_id'])
            
            if extract and tag:
                extract.tags.append(tag)
    
    def _backup_document_files(self, target_dir: str) -> bool:
        """
        Backup document files.
        
        Args:
            target_dir: Directory to save backup files
            
        Returns:
            True if backup successful, False otherwise
        """
        try:
            # Get all documents
            documents = self.db_session.query(Document).all()
            
            for document in documents:
                if os.path.exists(document.file_path):
                    # Calculate relative path for storage
                    rel_path = os.path.basename(document.file_path)
                    
                    # Create target path
                    target_path = os.path.join(target_dir, rel_path)
                    
                    # Copy file
                    shutil.copy(document.file_path, target_path)
            
            return True
            
        except Exception as e:
            logger.exception(f"Error backing up document files: {e}")
            return False
    
    def _restore_document_files(self, source_dir: str) -> bool:
        """
        Restore document files.
        
        Args:
            source_dir: Directory containing backup files
            
        Returns:
            True if restoration successful, False otherwise
        """
        try:
            # Get documents from the newly restored database
            documents = self.db_session.query(Document).all()
            
            # Create documents directory if it doesn't exist
            documents_dir = os.path.join(self.data_dir, "documents")
            os.makedirs(documents_dir, exist_ok=True)
            
            # Restore files and update paths
            for document in documents:
                # Get original filename
                orig_filename = os.path.basename(document.file_path)
                
                # Check if file exists in backup
                backup_file = os.path.join(source_dir, orig_filename)
                if os.path.exists(backup_file):
                    # Create new file path
                    new_path = os.path.join(documents_dir, orig_filename)
                    
                    # Copy file
                    shutil.copy(backup_file, new_path)
                    
                    # Update document path
                    document.file_path = new_path
            
            # Commit changes
            self.db_session.commit()
            
            return True
            
        except Exception as e:
            logger.exception(f"Error restoring document files: {e}")
            return False


# ui/backup_view.py

import os
import logging
import datetime
import humanize
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QCheckBox, QMessageBox, QFileDialog,
    QDialog, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QThread, QObject, QSize
from PyQt6.QtGui import QIcon

from core.knowledge_base.backup_manager import BackupManager

logger = logging.getLogger(__name__)

class BackupWorker(QObject):
    """Worker thread for backup operations."""
    
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int)
    
    def __init__(self, backup_manager, operation, **kwargs):
        super().__init__()
        self.backup_manager = backup_manager
        self.operation = operation
        self.kwargs = kwargs
    
    def run(self):
        """Run the backup operation."""
        result = False
        message = ""
        
        try:
            if self.operation == "create":
                include_files = self.kwargs.get("include_files", True)
                
                # Update progress
                self.progress.emit(10)
                
                backup_path = self.backup_manager.create_backup(include_files)
                
                # Update progress
                self.progress.emit(90)
                
                if backup_path:
                    result = True
                    message = f"Backup created: {os.path.basename(backup_path)}"
                else:
                    message = "Failed to create backup"
            
            elif self.operation == "restore":
                backup_path = self.kwargs.get("backup_path")
                
                # Update progress
                self.progress.emit(20)
                
                if backup_path:
                    result = self.backup_manager.restore_backup(backup_path)
                    
                    # Update progress
                    self.progress.emit(80)
                    
                    if result:
                        message = f"Backup restored: {os.path.basename(backup_path)}"
                    else:
                        message = f"Failed to restore backup: {os.path.basename(backup_path)}"
                else:
                    message = "No backup path specified"
            
            elif self.operation == "delete":
                backup_path = self.kwargs.get("backup_path")
                
                # Update progress
                self.progress.emit(50)
                
                if backup_path:
                    result = self.backup_manager.delete_backup(backup_path)
                    
                    if result:
                        message = f"Backup deleted: {os.path.basename(backup_path)}"
                    else:
                        message = f"Failed to delete backup: {os.path.basename(backup_path)}"
                else:
                    message = "No backup path specified"
            
            else:
                message = f"Unknown operation: {self.operation}"
        
        except Exception as e:
            result = False
            message = f"Error during backup operation: {str(e)}"
            logger.exception(message)
        
        # Update progress
        self.progress.emit(100)
        
        # Signal completion
        self.finished.emit(result, message)


class ProgressDialog(QDialog):
    """Dialog showing progress of a backup operation."""
    
    def __init__(self, title, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        self.status_label = QLabel("Operation in progress...")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # No close button
        self.setModal(True)
    
    def update_progress(self, value):
        """Update progress bar value."""
        self.progress_bar.setValue(value)
    
    def update_status(self, text):
        """Update status label text."""
        self.status_label.setText(text)


class BackupView(QWidget):
    """Widget for managing backups."""
    
    backup_complete = pyqtSignal(bool, str)
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.backup_manager = BackupManager(db_session)
        
        # Create UI
        self._create_ui()
        
        # Load backups
        self._load_backups()
        
        # Connect signals
        self.backup_complete.connect(self._on_backup_complete)
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header
        header_label = QLabel("Backup and Restore")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        main_layout.addWidget(header_label)
        
        # Create backup group
        create_group = QGroupBox("Create Backup")
        create_layout = QVBoxLayout(create_group)
        
        # Include files checkbox
        self.include_files_check = QCheckBox("Include document files")
        self.include_files_check.setChecked(True)
        create_layout.addWidget(self.include_files_check)
        
        # Create button
        create_button = QPushButton("Create Backup")
        create_button.clicked.connect(self._on_create_backup)
        create_layout.addWidget(create_button)
        
        main_layout.addWidget(create_group)
        
        # Existing backups group
        backups_group = QGroupBox("Existing Backups")
        backups_layout = QVBoxLayout(backups_group)
        
        # Backups list
        self.backups_list = QListWidget()
        self.backups_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.backups_list.itemSelectionChanged.connect(self._on_backup_selection_changed)
        backups_layout.addWidget(self.backups_list)
        
        # Backup actions
        actions_layout = QHBoxLayout()
        
        self.restore_button = QPushButton("Restore Selected")
        self.restore_button.clicked.connect(self._on_restore_backup)
        self.restore_button.setEnabled(False)  # Initially disabled
        actions_layout.addWidget(self.restore_button)
        
        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.clicked.connect(self._on_delete_backup)
        self.delete_button.setEnabled(False)  # Initially disabled
        actions_layout.addWidget(self.delete_button)
        
        self.export_button = QPushButton("Export Selected")
        self.export_button.clicked.connect(self._on_export_backup)
        self.export_button.setEnabled(False)  # Initially disabled
        actions_layout.addWidget(self.export_button)
        
        backups_layout.addLayout(actions_layout)
        
        # Import backup
        import_layout = QHBoxLayout()
        
        import_button = QPushButton("Import Backup")
        import_button.clicked.connect(self._on_import_backup)
        import_layout.addWidget(import_button)
        
        import_layout.addStretch()
        
        backups_layout.addLayout(import_layout)
        
        main_layout.addWidget(backups_group)
    
    def _load_backups(self):
        """Load the list of available backups."""
        self.backups_list.clear()
        
        backups = self.backup_manager.get_backup_list()
        
        for backup in backups:
            # Format item text
            timestamp_str = backup['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            size_str = humanize.naturalsize(backup['size'])
            files_str = "With files" if backup['has_files'] else "Database only"
            
            item_text = f"{timestamp_str} - {size_str} - {files_str}"
            
            # Create list item
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, backup['path'])
            
            self.backups_list.addItem(item)
    
    @pyqtSlot()
    def _on_backup_selection_changed(self):
        """Handle backup selection change."""
        selected_items = self.backups_list.selectedItems()
        has_selection = bool(selected_items)
        
        self.restore_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.export_button.setEnabled(has_selection)
    
    @pyqtSlot()
    def _on_create_backup(self):
        """Handle create backup button click."""
        include_files = self.include_files_check.isChecked()
        
        # Confirmation dialog
        msg = "Create a new backup"
        if include_files:
            msg += " including document files"
        msg += "?"
        
        reply = QMessageBox.question(
            self, "Create Backup", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Show progress dialog
            progress_dialog = ProgressDialog("Creating Backup", self)
            
            # Create worker thread
            self.thread = QThread()
            self.worker = BackupWorker(
                self.backup_manager, 
                "create", 
                include_files=include_files
            )
            self.worker.moveToThread(self.thread)
            
            # Connect signals
            self.thread.started.connect(self.worker.run)
            self.worker.progress.connect(progress_dialog.update_progress)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.finished.connect(progress_dialog.accept)
            self.worker.finished.connect(lambda result, message: self.backup_complete.emit(result, message))
            self.thread.finished.connect(self.thread.deleteLater)
            
            # Start thread
            self.thread.start()
            
            # Show dialog
            progress_dialog.exec()
    
    @pyqtSlot()
    def _on_restore_backup(self):
        """Handle restore backup button click."""
        selected_items = self.backups_list.selectedItems()
        if not selected_items:
            return
        
        backup_path = selected_items[0].data(Qt.ItemDataRole.UserRole)
        
        # Warning dialog
        reply = QMessageBox.warning(
            self, "Restore Backup", 
            "Restoring a backup will replace all current data. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Show progress dialog
            progress_dialog = ProgressDialog("Restoring Backup", self)
            
            # Create worker thread
            self.thread = QThread()
            self.worker = BackupWorker(
                self.backup_manager, 
                "restore", 
                backup_path=backup_path
            )
            self.worker.moveToThread(self.thread)
            
            # Connect signals
            self.thread.started.connect(self.worker.run)
            self.worker.progress.connect(progress_dialog.update_progress)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.finished.connect(progress_dialog.accept)
            self.worker.finished.connect(lambda result, message: self.backup_complete.emit(result, message))
            self.thread.finished.connect(self.thread.deleteLater)
            
            # Start thread
            self.thread.start()
            
            # Show dialog
            progress_dialog.exec()
    
    @pyqtSlot()
    def _on_delete_backup(self):
        """Handle delete backup button click."""
        selected_items = self.backups_list.selectedItems()
        if not selected_items:
            return
        
        backup_path = selected_items[0].data(Qt.ItemDataRole.UserRole)
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self, "Delete Backup", 
            "Are you sure you want to delete this backup?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Show progress dialog
            progress_dialog = ProgressDialog("Deleting Backup", self)
            
            # Create worker thread
            self.thread = QThread()
            self.worker = BackupWorker(
                self.backup_manager, 
                "delete", 
                backup_path=backup_path
            )
            self.worker.moveToThread(self.thread)
            
            # Connect signals
            self.thread.started.connect(self.worker.run)
            self.worker.progress.connect(progress_dialog.update_progress)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self.worker.deleteLater)
            self.worker.finished.connect(progress_dialog.accept)
            self.worker.finished.connect(lambda result, message: self.backup_complete.emit(result, message))
            self.thread.finished.connect(self.thread.deleteLater)
            
            # Start thread
            self.thread.start()
            
            # Show dialog
            progress_dialog.exec()
    
    @pyqtSlot()
    def _on_export_backup(self):
        """Handle export backup button click."""
        selected_items = self.backups_list.selectedItems()
        if not selected_items:
            return
        
        backup_path = selected_items[0].data(Qt.ItemDataRole.UserRole)
        
        # Get file name
        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        file_dialog.setNameFilter("Zip Files (*.zip)")
        file_dialog.setDefaultSuffix("zip")
        
        if file_dialog.exec():
            export_path = file_dialog.selectedFiles()[0]
            
            try:
                # Copy the file
                import shutil
                shutil.copy(backup_path, export_path)
                
                QMessageBox.information(
                    self, "Export Successful", 
                    f"Backup exported to: {export_path}"
                )
                
            except Exception as e:
                logger.exception(f"Error exporting backup: {e}")
                QMessageBox.warning(
                    self, "Export Failed", 
                    f"Failed to export backup: {str(e)}"
                )
    
    @pyqtSlot()
    def _on_import_backup(self):
        """Handle import backup button click."""
        # Get file name
        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter("Zip Files (*.zip)")
        
        if file_dialog.exec():
            import_path = file_dialog.selectedFiles()[0]
            
            # Warning dialog
            reply = QMessageBox.warning(
                self, "Import Backup", 
                "Importing a backup will replace all current data. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Show progress dialog
                progress_dialog = ProgressDialog("Importing Backup", self)
                
                # Create worker thread
                self.thread = QThread()
                self.worker = BackupWorker(
                    self.backup_manager, 
                    "restore", 
                    backup_path=import_path
                )
                self.worker.moveToThread(self.thread)
                
                # Connect signals
                self.thread.started.connect(self.worker.run)
                self.worker.progress.connect(progress_dialog.update_progress)
                self.worker.finished.connect(self.thread.quit)
                self.worker.finished.connect(self.worker.deleteLater)
                self.worker.finished.connect(progress_dialog.accept)
                self.worker.finished.connect(lambda result, message: self.backup_complete.emit(result, message))
                self.thread.finished.connect(self.thread.deleteLater)
                
                # Start thread
                self.thread.start()
                
                # Show dialog
                progress_dialog.exec()
    
    @pyqtSlot(bool, str)
    def _on_backup_complete(self, success, message):
        """Handle backup operation completion."""
        if success:
            QMessageBox.information(self, "Success", message)
            
            # Reload backups list
            self._load_backups()
        else:
            QMessageBox.warning(self, "Error", message)
