# ui/sync_view.py

import os
import logging
import datetime
from typing import Dict, Any, List, Optional
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QListWidget, QListWidgetItem,
    QGroupBox, QCheckBox, QMessageBox, QFileDialog,
    QDialog, QProgressBar, QLineEdit, QFormLayout,
    QComboBox, QTabWidget, QTextEdit, QGridLayout,
    QSizePolicy, QFrame, QSpacerItem, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QDateTime, QSize
from PyQt6.QtGui import QIcon, QPixmap

from core.utils.sync_manager import SyncManager, SUPPORTED_PROVIDERS
from core.utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class ProviderConfigDialog(QDialog):
    """Dialog for configuring a sync provider."""
    
    def __init__(self, provider_id: str, settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        
        self.provider_id = provider_id
        self.initial_settings = settings or {}
        self.result_settings = {}
        
        self.setWindowTitle(f"Configure {provider_id.replace('_', ' ').title()} Sync")
        self.setMinimumWidth(500)
        
        self._create_ui()
    
    def _create_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Provider-specific configuration form
        form_layout = QFormLayout()
        
        if self.provider_id == 'github':
            # GitHub configuration
            self.token_input = QLineEdit()
            self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.token_input.setText(self.initial_settings.get('token', ''))
            form_layout.addRow("Access Token:", self.token_input)
            
            self.repo_input = QLineEdit()
            self.repo_input.setPlaceholderText("username/repo")
            self.repo_input.setText(self.initial_settings.get('repo', ''))
            form_layout.addRow("Repository:", self.repo_input)
            
            self.branch_input = QLineEdit()
            self.branch_input.setText(self.initial_settings.get('branch', 'main'))
            form_layout.addRow("Branch:", self.branch_input)
            
            # Add a help text
            help_text = QLabel(
                "You need to create a GitHub Personal Access Token with 'repo' scope. "
                "Visit GitHub Settings > Developer Settings > Personal Access Tokens to create one."
            )
            help_text.setWordWrap(True)
            help_text.setStyleSheet("color: #666;")
            layout.addWidget(help_text)
            
        elif self.provider_id == 'google_drive':
            # Google Drive configuration
            self.credentials_input = QLineEdit()
            self.credentials_input.setText(self.initial_settings.get('credentials', ''))
            self.credentials_input.setReadOnly(True)
            form_layout.addRow("Credentials:", self.credentials_input)
            
            credentials_button = QPushButton("Select Credentials File...")
            credentials_button.clicked.connect(self._select_credentials_file)
            form_layout.addRow("", credentials_button)
            
            self.folder_id_input = QLineEdit()
            self.folder_id_input.setText(self.initial_settings.get('folder_id', ''))
            form_layout.addRow("Folder ID:", self.folder_id_input)
            
            # Add a help text
            help_text = QLabel(
                "You need to create a Google Cloud project and download OAuth credentials. "
                "The folder ID is the ID of the Google Drive folder where backups will be stored."
            )
            help_text.setWordWrap(True)
            help_text.setStyleSheet("color: #666;")
            layout.addWidget(help_text)
            
        elif self.provider_id == 'dropbox':
            # Dropbox configuration
            self.token_input = QLineEdit()
            self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.token_input.setText(self.initial_settings.get('token', ''))
            form_layout.addRow("Access Token:", self.token_input)
            
            self.folder_path_input = QLineEdit()
            self.folder_path_input.setText(self.initial_settings.get('folder_path', '/Incrementum'))
            form_layout.addRow("Folder Path:", self.folder_path_input)
            
            # Add a help text
            help_text = QLabel(
                "You need to create a Dropbox app and generate an access token. "
                "Visit Dropbox Developers and create an app with 'files.content.read' and 'files.content.write' scopes."
            )
            help_text.setWordWrap(True)
            help_text.setStyleSheet("color: #666;")
            layout.addWidget(help_text)
            
        elif self.provider_id == 'local':
            # Local folder configuration
            self.folder_path_input = QLineEdit()
            self.folder_path_input.setText(self.initial_settings.get('folder_path', ''))
            self.folder_path_input.setReadOnly(True)
            form_layout.addRow("Folder Path:", self.folder_path_input)
            
            folder_button = QPushButton("Select Folder...")
            folder_button.clicked.connect(self._select_folder)
            form_layout.addRow("", folder_button)
            
            # Add a help text
            help_text = QLabel(
                "Select a local folder to store backups. "
                "This folder can be on a network drive or cloud-synced folder (like OneDrive, Dropbox, etc.)"
            )
            help_text.setWordWrap(True)
            help_text.setStyleSheet("color: #666;")
            layout.addWidget(help_text)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._on_save)
        save_button.setDefault(True)
        button_layout.addWidget(save_button)
        
        layout.addLayout(button_layout)
    
    def _select_credentials_file(self):
        """Open file dialog to select Google credentials file."""
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        file_dialog.setNameFilter("JSON Files (*.json)")
        
        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            if selected_files:
                self.credentials_input.setText(selected_files[0])
    
    def _select_folder(self):
        """Open folder dialog to select sync folder."""
        folder_dialog = QFileDialog(self)
        folder_dialog.setFileMode(QFileDialog.FileMode.Directory)
        folder_dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        
        if folder_dialog.exec():
            selected_dirs = folder_dialog.selectedFiles()
            if selected_dirs:
                self.folder_path_input.setText(selected_dirs[0])
    
    def _on_save(self):
        """Handle save button click."""
        # Validate and collect settings
        if self.provider_id == 'github':
            token = self.token_input.text().strip()
            repo = self.repo_input.text().strip()
            branch = self.branch_input.text().strip()
            
            if not token or not repo:
                QMessageBox.warning(self, "Missing Information", "Please enter both token and repository.")
                return
            
            self.result_settings = {
                'token': token,
                'repo': repo,
                'branch': branch or 'main'
            }
            
        elif self.provider_id == 'google_drive':
            credentials = self.credentials_input.text().strip()
            folder_id = self.folder_id_input.text().strip()
            
            if not credentials or not folder_id:
                QMessageBox.warning(self, "Missing Information", "Please select credentials file and enter folder ID.")
                return
            
            self.result_settings = {
                'credentials': credentials,
                'folder_id': folder_id
            }
            
        elif self.provider_id == 'dropbox':
            token = self.token_input.text().strip()
            folder_path = self.folder_path_input.text().strip()
            
            if not token:
                QMessageBox.warning(self, "Missing Information", "Please enter an access token.")
                return
            
            self.result_settings = {
                'token': token,
                'folder_path': folder_path or '/Incrementum'
            }
            
        elif self.provider_id == 'local':
            folder_path = self.folder_path_input.text().strip()
            
            if not folder_path:
                QMessageBox.warning(self, "Missing Information", "Please select a folder.")
                return
            
            self.result_settings = {
                'folder_path': folder_path
            }
        
        # Accept the dialog
        self.accept()


class ProviderCardWidget(QWidget):
    """Widget for displaying a sync provider as a card."""
    
    configure_clicked = pyqtSignal(str)  # provider_id
    sync_clicked = pyqtSignal(str)  # provider_id
    
    def __init__(self, provider_info: Dict[str, Any], parent=None):
        super().__init__(parent)
        
        self.provider_info = provider_info
        self.provider_id = provider_info['id']
        
        self._create_ui()
    
    def _create_ui(self):
        """Create the card UI."""
        # Set up card appearance
        self.setMinimumHeight(150)
        self.setMaximumHeight(200)
        self.setMinimumWidth(250)
        
        # Add border and background
        self.setStyleSheet("""
            ProviderCardWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
            }
        """)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Header with icon and name
        header_layout = QHBoxLayout()
        
        # Provider icon
        icon_label = QLabel()
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "assets", "icons", self.provider_info.get('icon', 'sync.png')
        )
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio)
            icon_label.setPixmap(pixmap)
        else:
            icon_label.setText("🔄")
        
        icon_label.setFixedSize(32, 32)
        header_layout.addWidget(icon_label)
        
        # Provider name
        name_label = QLabel(f"<h3>{self.provider_info['name']}</h3>")
        header_layout.addWidget(name_label)
        
        # Status indicator
        self.status_indicator = QLabel()
        if self.provider_info.get('configured', False):
            self.status_indicator.setText("✅")
            self.status_indicator.setToolTip("Configured")
        else:
            self.status_indicator.setText("⚠️")
            self.status_indicator.setToolTip("Not configured")
        header_layout.addWidget(self.status_indicator)
        
        layout.addLayout(header_layout)
        
        # Description
        description_label = QLabel(self.provider_info['description'])
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        
        # Add a line separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Configure button
        self.configure_button = QPushButton("Configure")
        self.configure_button.clicked.connect(lambda: self.configure_clicked.emit(self.provider_id))
        button_layout.addWidget(self.configure_button)
        
        # Sync button
        self.sync_button = QPushButton("Sync")
        self.sync_button.clicked.connect(lambda: self.sync_clicked.emit(self.provider_id))
        self.sync_button.setEnabled(self.provider_info.get('configured', False))
        button_layout.addWidget(self.sync_button)
        
        layout.addLayout(button_layout)
    
    def update_status(self, configured: bool, last_sync: Optional[Dict[str, Any]] = None):
        """Update the provider status."""
        if configured:
            self.status_indicator.setText("✅")
            self.status_indicator.setToolTip("Configured")
            self.sync_button.setEnabled(True)
        else:
            self.status_indicator.setText("⚠️")
            self.status_indicator.setToolTip("Not configured")
            self.sync_button.setEnabled(False)


class SyncProgressDialog(QDialog):
    """Dialog showing sync progress."""
    
    def __init__(self, provider_name: str, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle(f"Syncing with {provider_name}")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        self.status_label = QLabel(f"Syncing with {provider_name}...")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # No close button
        self.setModal(True)
    
    @pyqtSlot(int, str)
    def update_progress(self, value, message):
        """Update progress bar and status message."""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)


class SyncView(QWidget):
    """Widget for managing cloud synchronization."""
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.sync_manager = SyncManager(db_session)
        self.settings_manager = SettingsManager()
        
        # Connect signals
        self.sync_manager.sync_started.connect(self._on_sync_started)
        self.sync_manager.sync_progress.connect(self._on_sync_progress)
        self.sync_manager.sync_completed.connect(self._on_sync_completed)
        self.sync_manager.sync_error.connect(self._on_sync_error)
        
        # Create UI
        self._create_ui()
        
        # Active dialogs
        self.progress_dialog = None
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header
        header_label = QLabel("<h2>Sync Knowledge Collection</h2>")
        main_layout.addWidget(header_label)
        
        # Description
        description = QLabel(
            "Sync your knowledge collection with cloud services to back up your data "
            "and work across multiple devices."
        )
        description.setWordWrap(True)
        main_layout.addWidget(description)
        
        # Sync providers grid
        providers_group = QGroupBox("Sync Providers")
        providers_layout = QGridLayout(providers_group)
        
        # Get providers
        providers = self.sync_manager.get_providers()
        
        # Create provider cards
        self.provider_cards = {}
        row, col = 0, 0
        max_cols = 2
        
        for provider in providers:
            card = ProviderCardWidget(provider)
            card.configure_clicked.connect(self._on_configure_provider)
            card.sync_clicked.connect(self._on_sync_provider)
            
            providers_layout.addWidget(card, row, col)
            self.provider_cards[provider['id']] = card
            
            # Update layout position
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        main_layout.addWidget(providers_group)
        
        # Sync history
        history_group = QGroupBox("Sync History")
        history_layout = QVBoxLayout(history_group)
        
        self.history_text = QTextEdit()
        self.history_text.setReadOnly(True)
        history_layout.addWidget(self.history_text)
        
        main_layout.addWidget(history_group)
        
        # Refresh history
        self._update_sync_history()
    
    def _update_sync_history(self):
        """Update the sync history display."""
        history_html = "<table width='100%'>"
        history_html += "<tr><th>Provider</th><th>Last Sync</th><th>Status</th></tr>"
        
        for provider in self.sync_manager.get_providers():
            provider_id = provider['id']
            provider_name = provider['name']
            
            last_sync = self.sync_manager.get_last_sync_info(provider_id)
            
            if last_sync:
                timestamp = datetime.datetime.fromisoformat(last_sync.get('timestamp', ''))
                timestamp_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                status = last_sync.get('status', 'Unknown')
                message = last_sync.get('message', '')
                
                if status == 'success':
                    status_html = f"<span style='color: green;'>✓ Success</span>"
                else:
                    status_html = f"<span style='color: red;'>✗ Failed</span>"
                
                history_html += f"<tr><td>{provider_name}</td><td>{timestamp_str}</td><td>{status_html}</td></tr>"
                
                if message:
                    history_html += f"<tr><td colspan='3'><small>{message}</small></td></tr>"
            else:
                history_html += f"<tr><td>{provider_name}</td><td>Never</td><td>-</td></tr>"
        
        history_html += "</table>"
        self.history_text.setHtml(history_html)
    
    @pyqtSlot(str)
    def _on_configure_provider(self, provider_id):
        """Handle configure button click."""
        # Get current settings
        settings = self.sync_manager.get_provider_settings(provider_id)
        
        # Show configuration dialog
        dialog = ProviderConfigDialog(provider_id, settings, self)
        
        if dialog.exec():
            # Get new settings
            new_settings = dialog.result_settings
            
            # Save settings
            success = self.sync_manager.configure_provider(provider_id, new_settings)
            
            if success:
                # Update provider card
                provider_info = next(p for p in self.sync_manager.get_providers() if p['id'] == provider_id)
                self.provider_cards[provider_id].update_status(True)
                
                QMessageBox.information(
                    self, "Provider Configured", 
                    f"{provider_info['name']} has been configured successfully."
                )
            else:
                QMessageBox.warning(
                    self, "Configuration Failed", 
                    f"Failed to configure {provider_id}. Please check your settings."
                )
    
    @pyqtSlot(str)
    def _on_sync_provider(self, provider_id):
        """Handle sync button click."""
        # Get provider info
        provider_info = next(p for p in self.sync_manager.get_providers() if p['id'] == provider_id)
        
        # Show confirmation
        reply = QMessageBox.question(
            self, "Confirm Sync", 
            f"Do you want to sync with {provider_info['name']}?\n\n"
            "This will back up your knowledge collection and check for updates.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Start sync
            self.sync_manager.sync(provider_id)
    
    @pyqtSlot(str)
    def _on_sync_started(self, provider_id):
        """Handle sync started signal."""
        # Get provider info
        provider_info = next(p for p in self.sync_manager.get_providers() if p['id'] == provider_id)
        
        # Show progress dialog
        self.progress_dialog = SyncProgressDialog(provider_info['name'], self)
        self.progress_dialog.show()
    
    @pyqtSlot(int, str)
    def _on_sync_progress(self, progress, message):
        """Handle sync progress signal."""
        if self.progress_dialog:
            self.progress_dialog.update_progress(progress, message)
    
    @pyqtSlot(bool, str)
    def _on_sync_completed(self, success, message):
        """Handle sync completed signal."""
        # Close progress dialog
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        # Show result
        if success:
            QMessageBox.information(self, "Sync Completed", message)
        else:
            QMessageBox.warning(self, "Sync Failed", message)
        
        # Update history
        self._update_sync_history()
    
    @pyqtSlot(str)
    def _on_sync_error(self, error_message):
        """Handle sync error signal."""
        # Show error (only if no completion message will be shown)
        if not self.progress_dialog:
            QMessageBox.critical(self, "Sync Error", error_message) 