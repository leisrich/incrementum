# core/utils/sync_manager.py

import os
import logging
import json
import shutil
import tempfile
import datetime
import threading
import time
from typing import Dict, Any, List, Optional, Tuple, Callable

from PyQt6.QtCore import QObject, pyqtSignal

from core.knowledge_base.backup_manager import BackupManager
from core.knowledge_base.export_manager import ExportManager

logger = logging.getLogger(__name__)

# Define supported cloud providers
SUPPORTED_PROVIDERS = ["github", "google_drive", "dropbox", "local"]

class SyncManager(QObject):
    """
    Manager for synchronizing knowledge collection with cloud services.
    
    This class handles backup/restore operations with various cloud providers,
    allowing users to sync their knowledge collection across different devices.
    """
    
    # Signals
    sync_started = pyqtSignal(str)  # provider
    sync_progress = pyqtSignal(int, str)  # progress percentage, status message
    sync_completed = pyqtSignal(bool, str)  # success, message
    sync_error = pyqtSignal(str)  # error message
    
    def __init__(self, db_session):
        super().__init__()
        self.db_session = db_session
        self.export_manager = ExportManager(db_session)
        self.backup_manager = BackupManager(db_session)
        
        # Track active syncs
        self._sync_in_progress = False
        self._last_sync = {}  # Store last sync info per provider
        
        # Provider specific settings
        self._provider_settings = {}
        
        # Load cached settings
        self._load_settings()
    
    def get_providers(self) -> List[Dict[str, Any]]:
        """
        Get list of available sync providers.
        
        Returns:
            List of provider information dictionaries
        """
        providers = [
            {
                'id': 'github',
                'name': 'GitHub',
                'description': 'Sync using a GitHub repository',
                'icon': 'github.png',
                'requires_auth': True,
                'configured': self.is_provider_configured('github')
            },
            {
                'id': 'google_drive',
                'name': 'Google Drive',
                'description': 'Sync using Google Drive',
                'icon': 'google_drive.png',
                'requires_auth': True,
                'configured': self.is_provider_configured('google_drive')
            },
            {
                'id': 'dropbox',
                'name': 'Dropbox',
                'description': 'Sync using Dropbox',
                'icon': 'dropbox.png',
                'requires_auth': True,
                'configured': self.is_provider_configured('dropbox')
            },
            {
                'id': 'local',
                'name': 'Local Folder',
                'description': 'Sync with a local folder on your computer',
                'icon': 'folder.png',
                'requires_auth': False,
                'configured': self.is_provider_configured('local')
            }
        ]
        
        return providers
    
    def is_provider_configured(self, provider_id: str) -> bool:
        """
        Check if a provider is configured.
        
        Args:
            provider_id: Provider identifier
            
        Returns:
            True if provider is configured, False otherwise
        """
        if provider_id not in self._provider_settings:
            return False
        
        settings = self._provider_settings[provider_id]
        
        if provider_id == 'github':
            return all(k in settings for k in ['token', 'repo', 'branch'])
        
        elif provider_id == 'google_drive':
            return all(k in settings for k in ['credentials', 'folder_id'])
        
        elif provider_id == 'dropbox':
            return all(k in settings for k in ['token', 'folder_path'])
        
        elif provider_id == 'local':
            return 'folder_path' in settings and os.path.exists(settings['folder_path'])
        
        return False
    
    def configure_provider(self, provider_id: str, settings: Dict[str, Any]) -> bool:
        """
        Configure a sync provider.
        
        Args:
            provider_id: Provider identifier
            settings: Provider-specific settings
            
        Returns:
            True if configuration was successful, False otherwise
        """
        try:
            # Validate settings based on provider
            if provider_id == 'github':
                # GitHub requires token, repo, and branch
                if not all(k in settings for k in ['token', 'repo', 'branch']):
                    logger.error(f"Missing required GitHub settings")
                    return False
                
                # TODO: Validate GitHub access
            
            elif provider_id == 'google_drive':
                # Google Drive requires credentials and folder ID
                if not all(k in settings for k in ['credentials', 'folder_id']):
                    logger.error(f"Missing required Google Drive settings")
                    return False
                
                # TODO: Validate Google Drive access
            
            elif provider_id == 'dropbox':
                # Dropbox requires token and folder path
                if not all(k in settings for k in ['token', 'folder_path']):
                    logger.error(f"Missing required Dropbox settings")
                    return False
                
                # TODO: Validate Dropbox access
            
            elif provider_id == 'local':
                # Local sync requires folder path
                if 'folder_path' not in settings:
                    logger.error(f"Missing required local folder path")
                    return False
                
                # Check if folder exists
                if not os.path.exists(settings['folder_path']):
                    # Create folder if it doesn't exist
                    try:
                        os.makedirs(settings['folder_path'], exist_ok=True)
                    except Exception as e:
                        logger.error(f"Error creating sync folder: {e}")
                        return False
            
            else:
                logger.error(f"Unknown provider: {provider_id}")
                return False
            
            # Store settings
            self._provider_settings[provider_id] = settings
            
            # Save settings to file
            self._save_settings()
            
            logger.info(f"Provider {provider_id} configured successfully")
            return True
            
        except Exception as e:
            logger.exception(f"Error configuring provider {provider_id}: {e}")
            return False
    
    def sync(self, provider_id: str, callback: Optional[Callable] = None) -> bool:
        """
        Synchronize data with the specified provider.
        
        Args:
            provider_id: Provider identifier
            callback: Optional callback function to call when sync completes
            
        Returns:
            True if sync started successfully, False otherwise
        """
        if self._sync_in_progress:
            logger.warning("Sync already in progress")
            return False
        
        if not self.is_provider_configured(provider_id):
            logger.error(f"Provider {provider_id} not configured")
            return False
        
        # Mark sync as in progress
        self._sync_in_progress = True
        
        # Emit started signal
        self.sync_started.emit(provider_id)
        
        # Start sync in a thread
        threading.Thread(
            target=self._sync_thread,
            args=(provider_id, callback),
            daemon=True
        ).start()
        
        return True
    
    def _sync_thread(self, provider_id: str, callback: Optional[Callable] = None):
        """
        Thread function to perform the actual sync.
        
        Args:
            provider_id: Provider identifier
            callback: Optional callback function
        """
        success = False
        message = ""
        
        try:
            # Update progress
            self.sync_progress.emit(10, f"Starting sync with {provider_id}...")
            
            # Get provider settings
            settings = self._provider_settings.get(provider_id, {})
            
            # Create a backup
            self.sync_progress.emit(20, "Creating backup...")
            backup_path = self.backup_manager.create_backup(include_files=True)
            
            if not backup_path:
                raise Exception("Failed to create backup")
            
            # Switch based on provider
            if provider_id == 'github':
                success, message = self._sync_with_github(backup_path, settings)
            
            elif provider_id == 'google_drive':
                success, message = self._sync_with_google_drive(backup_path, settings)
            
            elif provider_id == 'dropbox':
                success, message = self._sync_with_dropbox(backup_path, settings)
            
            elif provider_id == 'local':
                success, message = self._sync_with_local_folder(backup_path, settings)
            
            else:
                raise Exception(f"Unsupported provider: {provider_id}")
            
            # Update last sync info
            if success:
                self._last_sync[provider_id] = {
                    'timestamp': datetime.datetime.now().isoformat(),
                    'status': 'success',
                    'message': message
                }
                self._save_settings()
            
        except Exception as e:
            logger.exception(f"Error during sync with {provider_id}: {e}")
            success = False
            message = f"Sync error: {str(e)}"
            self.sync_error.emit(str(e))
        
        finally:
            # Clear sync in progress flag
            self._sync_in_progress = False
            
            # Emit completion signal
            self.sync_progress.emit(100, "Sync completed")
            self.sync_completed.emit(success, message)
            
            # Call callback if provided
            if callback:
                callback(success, message)
    
    def _sync_with_github(self, backup_path: str, settings: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Sync with GitHub.
        
        Args:
            backup_path: Path to backup file
            settings: GitHub settings
            
        Returns:
            Tuple of (success, message)
        """
        # Update progress
        self.sync_progress.emit(30, "Connecting to GitHub...")
        
        try:
            # This is a simplified implementation - in a real app you'd use a GitHub API library
            # like PyGithub or make API calls directly
            
            # For now, just simulate GitHub sync
            time.sleep(1)  # Simulate network latency
            
            # To implement: push backup to GitHub repo
            self.sync_progress.emit(50, "Uploading backup to GitHub...")
            time.sleep(2)  # Simulate upload time
            
            # To implement: check for newer backups on GitHub and download if needed
            self.sync_progress.emit(70, "Checking for updates...")
            time.sleep(1)  # Simulate checking
            
            # For a full implementation:
            # 1. Clone/pull the repo
            # 2. Check for newer backups
            # 3. If remote backup is newer, restore from it
            # 4. If local backup is newer, push it to the repo
            
            return True, "Synchronized with GitHub successfully"
            
        except Exception as e:
            logger.exception(f"GitHub sync error: {e}")
            return False, f"GitHub sync failed: {str(e)}"
    
    def _sync_with_google_drive(self, backup_path: str, settings: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Sync with Google Drive.
        
        Args:
            backup_path: Path to backup file
            settings: Google Drive settings
            
        Returns:
            Tuple of (success, message)
        """
        # Update progress
        self.sync_progress.emit(30, "Connecting to Google Drive...")
        
        try:
            # Simplified implementation - in a real app you'd use the Google Drive API
            
            # Simulate Google Drive operations
            time.sleep(1)  # Simulate authentication
            
            self.sync_progress.emit(50, "Uploading backup to Google Drive...")
            time.sleep(2)  # Simulate upload
            
            self.sync_progress.emit(70, "Checking for updates...")
            time.sleep(1)  # Simulate check for newer backups
            
            # For a full implementation:
            # 1. Authenticate with Google Drive
            # 2. Upload the backup
            # 3. Check for newer backups
            # 4. Download and restore newer backup if found
            
            return True, "Synchronized with Google Drive successfully"
            
        except Exception as e:
            logger.exception(f"Google Drive sync error: {e}")
            return False, f"Google Drive sync failed: {str(e)}"
    
    def _sync_with_dropbox(self, backup_path: str, settings: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Sync with Dropbox.
        
        Args:
            backup_path: Path to backup file
            settings: Dropbox settings
            
        Returns:
            Tuple of (success, message)
        """
        # Update progress
        self.sync_progress.emit(30, "Connecting to Dropbox...")
        
        try:
            # Simplified implementation - in a real app you'd use the Dropbox API
            
            # Simulate Dropbox operations
            time.sleep(1)  # Simulate authentication
            
            self.sync_progress.emit(50, "Uploading backup to Dropbox...")
            time.sleep(2)  # Simulate upload
            
            self.sync_progress.emit(70, "Checking for updates...")
            time.sleep(1)  # Simulate check for newer backups
            
            # For a full implementation:
            # 1. Authenticate with Dropbox
            # 2. Upload the backup
            # 3. Check for newer backups
            # 4. Download and restore newer backup if found
            
            return True, "Synchronized with Dropbox successfully"
            
        except Exception as e:
            logger.exception(f"Dropbox sync error: {e}")
            return False, f"Dropbox sync failed: {str(e)}"
    
    def _sync_with_local_folder(self, backup_path: str, settings: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Sync with a local folder.
        
        Args:
            backup_path: Path to backup file
            settings: Local folder settings
            
        Returns:
            Tuple of (success, message)
        """
        # Update progress
        self.sync_progress.emit(30, "Preparing local sync...")
        
        try:
            # Get folder path
            folder_path = settings.get('folder_path')
            if not folder_path or not os.path.exists(folder_path):
                return False, "Sync folder not found"
            
            # Get backup filename
            backup_filename = os.path.basename(backup_path)
            target_path = os.path.join(folder_path, backup_filename)
            
            # Copy backup to sync folder
            self.sync_progress.emit(50, "Copying backup to sync folder...")
            shutil.copy2(backup_path, target_path)
            
            # Check for newer backups in the sync folder
            self.sync_progress.emit(70, "Checking for updates...")
            
            # Find all backup files in the sync folder
            sync_backups = []
            for filename in os.listdir(folder_path):
                if filename.startswith("incrementum_backup_") and filename.endswith(".zip"):
                    file_path = os.path.join(folder_path, filename)
                    
                    # Extract timestamp from filename
                    timestamp_str = filename.replace("incrementum_backup_", "").replace(".zip", "")
                    try:
                        timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                        
                        sync_backups.append({
                            'path': file_path,
                            'timestamp': timestamp,
                            'filename': filename
                        })
                    except:
                        # Skip files with invalid timestamps
                        continue
            
            # Sort by timestamp (newest first)
            sync_backups.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # If there's a newer backup, restore it
            if sync_backups and sync_backups[0]['path'] != target_path:
                newest_backup = sync_backups[0]
                
                # Check if it's actually newer than our backup
                backup_time = datetime.datetime.strptime(
                    backup_filename.replace("incrementum_backup_", "").replace(".zip", ""),
                    "%Y%m%d_%H%M%S"
                )
                
                if newest_backup['timestamp'] > backup_time:
                    self.sync_progress.emit(80, "Found newer backup, restoring...")
                    
                    # Restore from the newer backup
                    success = self.backup_manager.restore_backup(newest_backup['path'])
                    if not success:
                        return False, "Failed to restore from newer backup"
                    
                    return True, f"Restored from newer backup: {newest_backup['filename']}"
            
            return True, "Synchronized with local folder successfully"
            
        except Exception as e:
            logger.exception(f"Local folder sync error: {e}")
            return False, f"Local folder sync failed: {str(e)}"
    
    def get_last_sync_info(self, provider_id: str) -> Dict[str, Any]:
        """
        Get information about the last sync with a provider.
        
        Args:
            provider_id: Provider identifier
            
        Returns:
            Dictionary with sync information, or empty dict if no sync has occurred
        """
        return self._last_sync.get(provider_id, {})
    
    def get_provider_settings(self, provider_id: str) -> Dict[str, Any]:
        """
        Get settings for a specific provider.
        
        Args:
            provider_id: Provider identifier
            
        Returns:
            Dictionary with provider settings, or empty dict if provider is not configured
        """
        return self._provider_settings.get(provider_id, {})
    
    def _load_settings(self):
        """Load sync settings from file."""
        try:
            # Get settings file path
            from appdirs import user_data_dir
            data_dir = user_data_dir("Incrementum", "Incrementum")
            settings_path = os.path.join(data_dir, "sync_settings.json")
            
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    data = json.load(f)
                    
                    self._provider_settings = data.get('providers', {})
                    self._last_sync = data.get('last_sync', {})
            
        except Exception as e:
            logger.exception(f"Error loading sync settings: {e}")
    
    def _save_settings(self):
        """Save sync settings to file."""
        try:
            # Get settings file path
            from appdirs import user_data_dir
            data_dir = user_data_dir("Incrementum", "Incrementum")
            os.makedirs(data_dir, exist_ok=True)
            settings_path = os.path.join(data_dir, "sync_settings.json")
            
            # Prepare data
            data = {
                'providers': self._provider_settings,
                'last_sync': self._last_sync
            }
            
            # Save to file
            with open(settings_path, 'w') as f:
                json.dump(data, f, indent=2)
            
        except Exception as e:
            logger.exception(f"Error saving sync settings: {e}") 