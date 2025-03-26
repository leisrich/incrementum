import os
import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QMessageBox, QComboBox, QProgressBar,
    QFormLayout, QCheckBox, QGroupBox, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.knowledge_base.models import YouTubePlaylist, YouTubePlaylistVideo, Category
from core.document_processor.handlers.youtube_handler import YouTubeHandler

logger = logging.getLogger(__name__)

class PlaylistImportWorker(QThread):
    """Worker thread for importing playlists to avoid UI freezing."""
    
    # Signals
    progress = pyqtSignal(int, str)  # Progress percentage, status message
    finished = pyqtSignal(bool, object, str)  # Success flag, playlist object, error message
    
    def __init__(self, playlist_url, category_id, db_session):
        super().__init__()
        self.playlist_url = playlist_url
        self.category_id = category_id
        self.db_session = db_session
        self.youtube_handler = YouTubeHandler()
        
    def run(self):
        """Run the import process."""
        try:
            # Extract playlist ID
            self.progress.emit(10, "Extracting playlist ID...")
            playlist_id = self.youtube_handler._extract_playlist_id(self.playlist_url)
            
            if not playlist_id:
                self.finished.emit(False, None, "Failed to extract playlist ID from URL.")
                return
                
            # Check if playlist already exists
            existing_playlist = self.db_session.query(YouTubePlaylist).filter_by(playlist_id=playlist_id).first()
            if existing_playlist:
                self.finished.emit(False, existing_playlist, "Playlist already exists in the database.")
                return
                
            # Fetch playlist metadata
            self.progress.emit(20, f"Fetching playlist metadata...")
            metadata = self.youtube_handler.fetch_playlist_metadata(playlist_id)
            
            if not metadata:
                self.finished.emit(False, None, "Failed to fetch playlist metadata.")
                return
                
            # Create playlist in database
            self.progress.emit(50, "Creating playlist in database...")
            new_playlist = YouTubePlaylist(
                playlist_id=playlist_id,
                title=metadata.get('title', f"YouTube Playlist {playlist_id}"),
                channel_title=metadata.get('channel_title', 'Unknown'),
                description=metadata.get('description', ''),
                thumbnail_url=metadata.get('thumbnail_url', ''),
                video_count=len(metadata.get('videos', [])),
                category_id=self.category_id,
                imported_date=datetime.utcnow(),
                last_updated=datetime.utcnow()
            )
            
            self.db_session.add(new_playlist)
            self.db_session.flush()  # Flush to get ID
            
            # Create video entries
            videos = metadata.get('videos', [])
            total_videos = len(videos)
            
            for i, video_data in enumerate(videos):
                # Update progress
                progress_pct = 50 + int((i / max(1, total_videos)) * 40)
                self.progress.emit(progress_pct, f"Processing video {i+1} of {total_videos}...")
                
                video_id = video_data.get('video_id')
                if not video_id:
                    continue
                    
                # Create video entry
                video = YouTubePlaylistVideo(
                    playlist_id=new_playlist.id,
                    video_id=video_id,
                    title=video_data.get('title', f"Video {i+1}"),
                    position=video_data.get('position', i+1),
                    duration=video_data.get('duration', 0)
                )
                
                self.db_session.add(video)
                
            # Commit all changes
            self.progress.emit(95, "Committing changes to database...")
            self.db_session.commit()
            
            # Done
            self.progress.emit(100, "Playlist import complete.")
            self.finished.emit(True, new_playlist, "")
            
        except Exception as e:
            logger.exception(f"Error importing playlist: {e}")
            self.db_session.rollback()
            self.finished.emit(False, None, f"Error importing playlist: {str(e)}")

class ImportYouTubePlaylistDialog(QDialog):
    """Dialog for importing YouTube playlists."""
    
    def __init__(self, db_session, parent=None):
        super().__init__(parent)
        self.db_session = db_session
        self.youtube_handler = YouTubeHandler()
        
        self.setWindowTitle("Import YouTube Playlist")
        self.setMinimumWidth(500)
        
        self._create_ui()
        self._load_categories()
        
    def _create_ui(self):
        """Create the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Form layout for inputs
        form_layout = QFormLayout()
        
        # URL input
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/playlist?list=...")
        form_layout.addRow("Playlist URL:", self.url_input)
        
        # Category dropdown
        self.category_combo = QComboBox()
        form_layout.addRow("Category:", self.category_combo)
        
        # Add form to main layout
        layout.addLayout(form_layout)
        
        # Options group
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)
        
        # Create documents checkbox
        self.create_docs_checkbox = QCheckBox("Create document entries for videos")
        self.create_docs_checkbox.setChecked(True)
        self.create_docs_checkbox.setToolTip("Create document entries in the knowledge base for each video")
        options_layout.addWidget(self.create_docs_checkbox)
        
        # Download thumbnails checkbox
        self.download_thumbs_checkbox = QCheckBox("Download video thumbnails")
        self.download_thumbs_checkbox.setChecked(True)
        self.download_thumbs_checkbox.setToolTip("Download and store thumbnail images for videos")
        options_layout.addWidget(self.download_thumbs_checkbox)
        
        layout.addWidget(options_group)
        
        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Test button
        self.test_button = QPushButton("Test URL")
        self.test_button.clicked.connect(self._on_test_url)
        button_layout.addWidget(self.test_button)
        
        button_layout.addStretch()
        
        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        # Import button
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self._on_import)
        self.import_button.setDefault(True)
        button_layout.addWidget(self.import_button)
        
        layout.addLayout(button_layout)
        
    def _load_categories(self):
        """Load categories into the combo box."""
        try:
            # Get all categories
            categories = self.db_session.query(Category).order_by(Category.name).all()
            
            # Add to combo box
            self.category_combo.addItem("(No Category)", None)
            
            for category in categories:
                self.category_combo.addItem(category.name, category.id)
                
        except Exception as e:
            logger.exception(f"Error loading categories: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load categories: {str(e)}")
            
    def _on_test_url(self):
        """Test the entered URL to see if it's a valid YouTube playlist."""
        url = self.url_input.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a playlist URL.")
            return
            
        try:
            # Extract playlist ID
            playlist_id = self.youtube_handler._extract_playlist_id(url)
            
            if not playlist_id:
                QMessageBox.warning(self, "Invalid URL", "The URL does not appear to be a YouTube playlist.")
                return
                
            # Check if playlist already exists
            existing_playlist = self.db_session.query(YouTubePlaylist).filter_by(playlist_id=playlist_id).first()
            if existing_playlist:
                QMessageBox.information(
                    self, 
                    "Playlist Exists", 
                    f"This playlist already exists in your library:\n{existing_playlist.title}"
                )
                return
                
            # Fetch basic playlist info
            self.status_label.setText("Fetching playlist info...")
            QApplication.processEvents()
            
            metadata = self.youtube_handler.fetch_playlist_metadata(playlist_id)
            
            if not metadata:
                QMessageBox.warning(self, "Error", "Failed to fetch playlist information.")
                self.status_label.setText("")
                return
                
            # Show playlist info
            videos_count = len(metadata.get('videos', []))
            
            info_text = (
                f"Playlist: {metadata.get('title')}\n"
                f"Channel: {metadata.get('channel_title')}\n"
                f"Videos: {videos_count}"
            )
            
            QMessageBox.information(self, "Playlist Info", info_text)
            self.status_label.setText(f"Valid playlist: {metadata.get('title')} ({videos_count} videos)")
            
        except Exception as e:
            logger.exception(f"Error testing playlist URL: {e}")
            QMessageBox.warning(self, "Error", f"Failed to test playlist URL: {str(e)}")
            self.status_label.setText("")
            
    def _on_import(self):
        """Import the playlist."""
        url = self.url_input.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a playlist URL.")
            return
            
        # Get selected category
        category_id = self.category_combo.currentData()
        
        # Confirm import
        result = QMessageBox.question(
            self,
            "Import Playlist",
            "Are you sure you want to import this playlist?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if result != QMessageBox.StandardButton.Yes:
            return
            
        # Disable inputs during import
        self._set_inputs_enabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        # Create worker thread
        self.import_worker = PlaylistImportWorker(url, category_id, self.db_session)
        self.import_worker.progress.connect(self._on_import_progress)
        self.import_worker.finished.connect(self._on_import_finished)
        self.import_worker.start()
        
    def _on_import_progress(self, progress, message):
        """Handle progress updates from the worker thread."""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
        QApplication.processEvents()
        
    def _on_import_finished(self, success, playlist, error_msg):
        """Handle import completion."""
        self.progress_bar.setVisible(False)
        
        if success:
            QMessageBox.information(
                self,
                "Import Complete",
                f"Playlist '{playlist.title}' imported successfully with {len(playlist.videos)} videos."
            )
            self.accept()  # Close dialog with success
        else:
            if playlist:  # Playlist exists
                QMessageBox.warning(
                    self,
                    "Import Failed",
                    f"{error_msg}\n\nPlaylist '{playlist.title}' already exists in your library."
                )
            else:
                QMessageBox.warning(self, "Import Failed", error_msg)
                
            # Re-enable inputs for retry
            self._set_inputs_enabled(True)
        
    def _set_inputs_enabled(self, enabled):
        """Enable or disable input widgets."""
        self.url_input.setEnabled(enabled)
        self.category_combo.setEnabled(enabled)
        self.create_docs_checkbox.setEnabled(enabled)
        self.download_thumbs_checkbox.setEnabled(enabled)
        self.test_button.setEnabled(enabled)
        self.import_button.setEnabled(enabled)
