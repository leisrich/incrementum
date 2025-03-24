# ui/backup_view.py

import os
import logging
import datetime
import humanize
from typing import Dict, Any, List, Optional
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QCheckBox, QMessageBox, QFileDialog,
    QDialog, QProgressBar, QProgressDialog, QRadioButton,
    QButtonGroup, QFormLayout, QSpinBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QDateTime, QThread, QObject
from PyQt6.QtGui import QIcon

from core.knowledge_base.models import init_database
from core.knowledge_base.export_manager import ExportManager
from core.utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class BackupWorker(QObject):
    """Worker thread for backup operations."""
    
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int, str)
    
    def __init__(self, db_session, operation, **kwargs):
        super().__init__()
        self.db_session = db_session
        self.export_manager = ExportManager(db_session)
        self.operation = operation
        self.kwargs = kwargs
    
    def run(self):
        """Run the backup operation."""
        result = False
        message = ""
        
        try:
            if self.operation == "create":
                # Update progress
                self.progress.emit(10, "Preparing backup...")
                
                # Get parameters
                include_files = self.kwargs.get("include_files", True)
                filepath = self.kwargs.get("filepath", None)
                
                # Create backup
                self.progress.emit(20, "Creating backup...")
                if filepath:
                    # Create a backup at a specific location
                    backup_path = filepath
                    
                    # Get extract IDs to include - include all extracts by default
                    extract_ids = self.kwargs.get("extract_ids", None)
                    if extract_ids is None:
                        # Get all extract IDs
                        from core.knowledge_base.models import Extract
                        extracts = self.db_session.query(Extract).all()
                        extract_ids = [extract.id for extract in extracts]
                    
                    # Export as a deck
                    result = self.export_manager.export_deck(extract_ids, backup_path)
                else:
                    # Let the export manager create the backup in the default location
                    backup_path = self.export_manager.create_backup(include_files)
                    result = backup_path is not None
                
                # Update progress
                self.progress.emit(90, "Finalizing backup...")
                
                if result:
                    message = f"Backup created successfully: {os.path.basename(backup_path)}"
                else:
                    message = "Failed to create backup"
            
            elif self.operation == "restore":
                # Get parameters
                backup_path = self.kwargs.get("backup_path")
                
                if not backup_path:
                    message = "No backup path specified"
                    result = False
                else:
                    # Update progress
                    self.progress.emit(20, "Reading backup file...")
                    
                    # Check if it's a native backup or a deck
                    if backup_path.lower().endswith('.izd'):
                        # Restore from deck
                        self.progress.emit(40, "Importing deck...")
                        extracts, items, tags = self.export_manager.import_deck(backup_path)
                        result = extracts > 0 or items > 0
                        
                        if result:
                            message = f"Restored {extracts} extracts, {items} items, and {tags} tags"
                        else:
                            message = "Failed to restore from deck"
                    else:
                        # Restore native backup
                        self.progress.emit(40, "Restoring database...")
                        result = self.export_manager.restore_backup(backup_path)
                        
                        if result:
                            message = "Backup restored successfully"
                        else:
                            message = "Failed to restore backup"
                
                # Update progress
                self.progress.emit(90, "Finalizing restore...")
            
            elif self.operation == "delete":
                # Get parameters
                backup_path = self.kwargs.get("backup_path")
                
                if not backup_path:
                    message = "No backup path specified"
                    result = False
                else:
                    # Update progress
                    self.progress.emit(40, "Deleting backup...")
                    
                    # Delete the backup
                    result = self.export_manager.delete_backup(backup_path)
                    
                    if result:
                        message = f"Backup deleted: {os.path.basename(backup_path)}"
                    else:
                        message = f"Failed to delete backup: {os.path.basename(backup_path)}"
                
                # Update progress
                self.progress.emit(90, "Done")
            
            else:
                message = f"Unknown operation: {self.operation}"
                result = False
        
        except Exception as e:
            result = False
            message = f"Error during backup operation: {str(e)}"
            logger.exception(message)
        
        # Update progress
        self.progress.emit(100, "Operation completed")
        
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
    
    @pyqtSlot(int, str)
    def update_progress(self, value, text):
        """Update progress bar value and status text."""
        self.progress_bar.setValue(value)
        self.status_label.setText(text)


class BackupView(QWidget):
    """Widget for managing backups and restores."""
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.export_manager = ExportManager(db_session)
        self.settings_manager = SettingsManager()
        
        # Create UI
        self._create_ui()
        
        # Load backups
        self._load_backups()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header
        header_label = QLabel("<h2>Backup and Restore</h2>")
        main_layout.addWidget(header_label)
        
        # Description
        description = QLabel("Create backups of your knowledge base and restore from previous backups.")
        main_layout.addWidget(description)
        
        # Split into two columns
        columns_layout = QHBoxLayout()
        
        # Left column - Create backup
        left_column = QVBoxLayout()
        
        # Create backup group
        create_group = QGroupBox("Create Backup")
        create_layout = QVBoxLayout(create_group)
        
        # Backup type
        type_layout = QHBoxLayout()
        
        self.backup_type_group = QButtonGroup(self)
        
        self.full_backup_radio = QRadioButton("Full Backup")
        self.full_backup_radio.setChecked(True)
        self.backup_type_group.addButton(self.full_backup_radio)
        type_layout.addWidget(self.full_backup_radio)
        
        self.selected_radio = QRadioButton("Selected Content")
        self.backup_type_group.addButton(self.selected_radio)
        type_layout.addWidget(self.selected_radio)
        
        create_layout.addLayout(type_layout)
        
        # Include files checkbox
        self.include_files_check = QCheckBox("Include document files")
        self.include_files_check.setChecked(True)
        create_layout.addWidget(self.include_files_check)
        
        # Auto-backup options
        auto_backup_group = QGroupBox("Auto-Backup Settings")
        auto_backup_layout = QFormLayout(auto_backup_group)
        
        self.auto_backup_check = QCheckBox()
        auto_backup_enabled = self.settings_manager.get_setting("backup", "auto_backup_enabled", True)
        self.auto_backup_check.setChecked(auto_backup_enabled)
        self.auto_backup_check.stateChanged.connect(self._on_auto_backup_changed)
        auto_backup_layout.addRow("Enable auto-backup:", self.auto_backup_check)
        
        self.auto_backup_interval = QSpinBox()
        self.auto_backup_interval.setRange(1, 90)
        self.auto_backup_interval.setSuffix(" days")
        auto_backup_interval = self.settings_manager.get_setting("backup", "auto_backup_interval", 7)
        self.auto_backup_interval.setValue(auto_backup_interval)
        auto_backup_layout.addRow("Interval:", self.auto_backup_interval)
        
        self.auto_backup_count = QSpinBox()
        self.auto_backup_count.setRange(1, 20)
        auto_backup_count = self.settings_manager.get_setting("backup", "auto_backup_count", 5)
        self.auto_backup_count.setValue(auto_backup_count)
        auto_backup_layout.addRow("Keep backups:", self.auto_backup_count)
        
        create_layout.addWidget(auto_backup_group)
        
        # Create button
        create_button = QPushButton("Create Backup")
        create_button.clicked.connect(self._on_create_backup)
        create_layout.addWidget(create_button)
        
        left_column.addWidget(create_group)
        
        # Right column - Existing backups
        right_column = QVBoxLayout()
        
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
        
        refresh_button = QPushButton("Refresh List")
        refresh_button.clicked.connect(self._on_refresh)
        import_layout.addWidget(refresh_button)
        
        backups_layout.addLayout(import_layout)
        
        right_column.addWidget(backups_group)
        
        # Add columns to layout
        columns_layout.addLayout(left_column)
        columns_layout.addLayout(right_column)
        
        main_layout.addLayout(columns_layout)
    
    def _load_backups(self):
        """Load the list of available backups."""
        self.backups_list.clear()
        
        try:
            backups = self.export_manager.get_backup_list()
            
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
        except Exception as e:
            logger.exception(f"Error loading backups: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to load backups: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_backup_selection_changed(self):
        """Handle backup selection change."""
        selected_items = self.backups_list.selectedItems()
        has_selection = bool(selected_items)
        
        self.restore_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.export_button.setEnabled(has_selection)
    
    @pyqtSlot(int)
    def _on_auto_backup_changed(self, state):
        """Handle auto-backup setting change."""
        enabled = state == Qt.CheckState.Checked.value
        
        # Update settings
        self.settings_manager.set_setting("backup", "auto_backup_enabled", enabled)
        self.settings_manager.set_setting("backup", "auto_backup_interval", self.auto_backup_interval.value())
        self.settings_manager.set_setting("backup", "auto_backup_count", self.auto_backup_count.value())
        self.settings_manager.save_settings()
    
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
            if self.full_backup_radio.isChecked():
                # Full backup
                self._run_backup_operation("create", include_files=include_files)
            else:
                # Selected content backup - would normally show a selection dialog
                # For now, just export all content to a file
                filepath, _ = QFileDialog.getSaveFileName(
                    self, "Save Backup", "", "Incrementum Deck Files (*.izd)"
                )
                
                if filepath:
                    if not filepath.lower().endswith('.izd'):
                        filepath += '.izd'
                    
                    self._run_backup_operation("create", include_files=include_files, filepath=filepath)
    
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
            self._run_backup_operation("restore", backup_path=backup_path)
    
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
            self._run_backup_operation("delete", backup_path=backup_path)
    
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
        
        # Determine appropriate file extension
        if backup_path.lower().endswith('.izd'):
            filter_str = "Incrementum Deck Files (*.izd)"
            default_ext = '.izd'
        else:
            filter_str = "Zip Files (*.zip)"
            default_ext = '.zip'
        
        file_dialog.setNameFilter(filter_str)
        file_dialog.setDefaultSuffix(default_ext[1:])  # Remove leading dot
        
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
        file_dialog.setNameFilter("Backup Files (*.zip *.izd)")
        
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
                self._run_backup_operation("restore", backup_path=import_path)
    
    @pyqtSlot()
    def _on_refresh(self):
        """Handle refresh button click."""
        self._load_backups()
    
    def _run_backup_operation(self, operation, **kwargs):
        """
        Run a backup operation with progress dialog.
        
        Args:
            operation: Operation type ('create', 'restore', 'delete')
            **kwargs: Operation-specific parameters
        """
        # Create progress dialog
        if operation == "create":
            title = "Creating Backup"
        elif operation == "restore":
            title = "Restoring Backup"
        elif operation == "delete":
            title = "Deleting Backup"
        else:
            title = "Backup Operation"
        
        progress_dialog = ProgressDialog(title, self)
        
        # Create worker and thread
        self.worker = BackupWorker(self.db_session, operation, **kwargs)
        self.thread = QThread()
        
        # Move worker to thread
        self.worker.moveToThread(self.thread)
        
        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(progress_dialog.update_progress)
        self.worker.finished.connect(self._on_backup_operation_finished)
        self.worker.finished.connect(progress_dialog.accept)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        # Start thread
        self.thread.start()
        
        # Show dialog
        progress_dialog.exec()
    
    @pyqtSlot(bool, str)
    def _on_backup_operation_finished(self, success, message):
        """Handle backup operation completion."""
        if success:
            QMessageBox.information(self, "Success", message)
            # Reload backups list
            self._load_backups()
        else:
            QMessageBox.warning(self, "Error", message)
