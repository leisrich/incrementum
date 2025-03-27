import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QMenu, QMessageBox,
    QScrollArea, QFrame, QSizePolicy, QProgressBar, QToolButton, QToolBar,
    QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize, QUrl
from PyQt6.QtGui import QIcon, QAction, QDesktopServices, QPixmap
from PyQt6.QtWebEngineWidgets import QWebEngineView

from core.knowledge_base.models import YouTubePlaylist, YouTubePlaylistVideo, Category, Document
from core.document_processor.handlers.youtube_handler import YouTubeHandler

logger = logging.getLogger(__name__)

class VideoListItem(QListWidgetItem):
    """Custom list widget item for videos in a playlist."""
    
    def __init__(self, playlist_video: YouTubePlaylistVideo, video_metadata: Dict[str, Any]):
        super().__init__()
        self.playlist_video = playlist_video
        self.video_metadata = video_metadata
        self.video_id = playlist_video.video_id
        
        # Set fixed height for consistent look
        self.setSizeHint(QSize(0, 60))
        
        # Format the display text
        self._update_display_text()
        
    def _update_display_text(self):
        """Update the display text based on the current state."""
        # Format duration for display
        duration_text = self._format_duration(self.playlist_video.duration)
        
        # Format progress
        if self.playlist_video.is_watched:
            progress_text = "✓ "  # Checkmark for watched videos
        elif self.playlist_video.watched_position > 0:
            progress = int(self.playlist_video.watched_percent)
            progress_text = f"▶ {progress}% "  # Play symbol with progress
        else:
            progress_text = ""
            
        # Build display text with position number, title, and duration
        position_text = f"{self.playlist_video.position:02d}. "  # Zero-padded position
        title_text = self.playlist_video.title
        
        # Truncate title if too long
        if len(title_text) > 60:
            title_text = title_text[:57] + "..."
            
        # Combine all parts with proper formatting
        text = f"{position_text}{progress_text}{title_text}\n"
        text += f"Duration: {duration_text}"
        
        self.setText(text)
        
        # Set tooltip with full title
        self.setToolTip(self.playlist_video.title)
        
    def _format_duration(self, seconds: int) -> str:
        """Format seconds as HH:MM:SS or MM:SS."""
        if seconds < 3600:
            return f"{seconds // 60}:{seconds % 60:02d}"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            seconds = seconds % 60
            return f"{hours}:{minutes:02d}:{seconds:02d}"
            
    def update_progress(self):
        """Update the display text after progress change."""
        self._update_display_text()

class YouTubePlaylistView(QWidget):
    """Widget for displaying and interacting with YouTube playlists."""
    
    # Signals
    playlistSelected = pyqtSignal(int)  # Emitted when a playlist is selected (playlist_id)
    videoSelected = pyqtSignal(str, int)  # Emitted when a video is selected (video_id, position)
    
    def __init__(self, db_session, parent=None):
        super().__init__(parent)
        self.db_session = db_session
        self.youtube_handler = YouTubeHandler()
        self.current_playlist = None
        self.current_playlist_videos = []
        
        # Setup UI
        self._create_ui()
        
        # Load playlists
        self._load_playlists()
        
    def _create_ui(self):
        """Create the user interface."""
        main_layout = QVBoxLayout(self)
        
        # Header with import button
        header_layout = QHBoxLayout()
        
        title_label = QLabel("YouTube Playlists")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        import_btn = QPushButton("Import Playlist")
        import_btn.setIcon(QIcon.fromTheme("list-add"))
        import_btn.setToolTip("Import a new YouTube playlist by URL")
        import_btn.clicked.connect(self._on_import_playlist)
        header_layout.addWidget(import_btn)
        
        main_layout.addLayout(header_layout)
        
        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Playlists
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Playlist list
        self.playlist_list = QListWidget()
        self.playlist_list.setMinimumWidth(200)
        self.playlist_list.itemClicked.connect(self._on_playlist_selected)
        self.playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self._on_playlist_context_menu)
        left_layout.addWidget(self.playlist_list)
        
        splitter.addWidget(left_widget)
        
        # Right side: Videos in playlist
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Playlist info section
        self.playlist_info = QLabel("Select a playlist from the left or import a new one.")
        self.playlist_info.setWordWrap(True)
        self.playlist_info.setStyleSheet("padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        right_layout.addWidget(self.playlist_info)
        
        # Playlist actions toolbar
        actions_toolbar = QToolBar()
        actions_toolbar.setIconSize(QSize(16, 16))
        
        self.play_all_action = QAction(QIcon.fromTheme("media-playback-start"), "Play All", self)
        self.play_all_action.setToolTip("Play all videos starting from the first unwatched")
        self.play_all_action.triggered.connect(self._on_play_all)
        actions_toolbar.addAction(self.play_all_action)
        
        self.refresh_action = QAction(QIcon.fromTheme("view-refresh"), "Refresh", self)
        self.refresh_action.setToolTip("Update playlist details and videos from YouTube")
        self.refresh_action.triggered.connect(self._on_refresh_playlist)
        actions_toolbar.addAction(self.refresh_action)
        
        right_layout.addWidget(actions_toolbar)
        
        # Video list
        self.video_list = QListWidget()
        self.video_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.video_list.customContextMenuRequested.connect(self._on_video_context_menu)
        self.video_list.itemDoubleClicked.connect(self._on_video_double_clicked)
        self.video_list.setMinimumWidth(300)  # Set minimum width
        self.video_list.setStyleSheet("""
            QListWidget {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #dee2e6;
            }
            QListWidget::item:selected {
                background-color: #e9ecef;
                color: black;
            }
            QListWidget::item:hover {
                background-color: #f1f3f5;
            }
        """)
        right_layout.addWidget(self.video_list)
        
        splitter.addWidget(right_widget)
        
        # Set initial splitter sizes
        splitter.setSizes([250, 550])
        
        main_layout.addWidget(splitter)
        
    def _load_playlists(self):
        """Load playlists from the database."""
        try:
            # Clear current list
            self.playlist_list.clear()
            
            # Query playlists from database with video count
            playlists = self.db_session.query(YouTubePlaylist).order_by(YouTubePlaylist.title).all()
            
            # Add to list widget
            for playlist in playlists:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, playlist.id)
                
                # Get actual video count from database
                video_count = self.db_session.query(YouTubePlaylistVideo)\
                    .filter_by(playlist_id=playlist.id)\
                    .count()
                
                # Update playlist title with video count
                item.setText(f"{playlist.title} ({video_count} videos)")
                item.setToolTip(f"Channel: {playlist.channel_title}\nClick to view videos.")
                self.playlist_list.addItem(item)
                
            # Show a message if no playlists
            if len(playlists) == 0:
                self.playlist_info.setText("No playlists found. Click 'Import Playlist' above to add one.")
                self.video_list.clear()
                self.current_playlist = None
                
            logger.info(f"Loaded {len(playlists)} playlists")
                
        except Exception as e:
            logger.exception(f"Error loading playlists: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load playlists: {str(e)}")
            
    def _on_playlist_selected(self, item):
        """Handle playlist selection."""
        try:
            # Get playlist ID from item data
            playlist_id = item.data(Qt.ItemDataRole.UserRole)
            
            # Query playlist from database
            playlist = self.db_session.query(YouTubePlaylist).filter_by(id=playlist_id).first()
            
            if not playlist:
                QMessageBox.warning(self, "Error", "Playlist not found in database.")
                return
                
            # Store current playlist
            self.current_playlist = playlist
            
            # Update playlist info display
            self._update_playlist_info(playlist)
            
            # Load videos for this playlist
            self._load_playlist_videos(playlist)
            
            # Emit signal
            self.playlistSelected.emit(playlist_id)
            
        except Exception as e:
            logger.exception(f"Error selecting playlist: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load playlist: {str(e)}")
            
    def _update_playlist_info(self, playlist):
        """Update the playlist info display."""
        info_text = f"<h3>{playlist.title}</h3>"
        info_text += f"<p><b>Channel:</b> {playlist.channel_title}</p>"
        
        if playlist.description:
            # Truncate description if too long
            desc = playlist.description
            if len(desc) > 200:
                desc = desc[:200] + "..."
            info_text += f"<p>{desc}</p>"
            
        # Get video count directly from the database
        video_count = self.db_session.query(YouTubePlaylistVideo).filter_by(playlist_id=playlist.id).count()
        last_updated = playlist.last_updated.strftime("%Y-%m-%d %H:%M") if playlist.last_updated else "Never"
        
        info_text += f"<p><b>Videos:</b> {video_count} | <b>Last updated:</b> {last_updated}</p>"
        
        self.playlist_info.setText(info_text)
        
    def _load_playlist_videos(self, playlist):
        """Load videos for a playlist."""
        try:
            # Clear current list
            self.video_list.clear()
            
            # Query videos from database, ordered by position
            videos = self.db_session.query(YouTubePlaylistVideo)\
                .filter_by(playlist_id=playlist.id)\
                .order_by(YouTubePlaylistVideo.position)\
                .all()
            
            # Store for later use
            self.current_playlist_videos = videos
            
            if not videos:
                logger.warning(f"No videos found for playlist {playlist.id}")
                self.video_list.addItem("No videos found in this playlist")
                return
                
            # Add to list widget
            for video in videos:
                # Create metadata dictionary
                metadata = {
                    'video_id': video.video_id,
                    'title': video.title,
                    'position': video.position,
                    'duration': video.duration
                }
                
                # Create and add list item
                item = VideoListItem(video, metadata)
                self.video_list.addItem(item)
                
            logger.info(f"Loaded {len(videos)} videos for playlist {playlist.id}")
            
        except Exception as e:
            logger.exception(f"Error loading playlist videos: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load videos: {str(e)}")
            
    def _on_video_double_clicked(self, item):
        """Handle video double-click to play the video."""
        if isinstance(item, VideoListItem):
            video = item.playlist_video
            self.videoSelected.emit(video.video_id, video.position)
            
    def _on_video_context_menu(self, position):
        """Show context menu for video items."""
        # Get item at position
        item = self.video_list.itemAt(position)
        
        if not item or not isinstance(item, VideoListItem):
            return
            
        video = item.playlist_video
        
        # Create context menu
        menu = QMenu(self)
        
        # Add actions
        play_action = QAction("Play Video", self)
        play_action.triggered.connect(lambda: self.videoSelected.emit(video.video_id, video.position))
        menu.addAction(play_action)
        
        # Add "Open in Browser" action
        open_browser_action = QAction("Open in Web Browser", self)
        open_browser_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/watch?v={video.video_id}")))
        menu.addAction(open_browser_action)
        
        menu.addSeparator()
        
        # Add "Mark as Watched" or "Mark as Unwatched" based on current state
        if video.is_watched:
            mark_action = QAction("Mark as Unwatched", self)
            mark_action.triggered.connect(lambda: self._mark_video_unwatched(video, item))
        else:
            mark_action = QAction("Mark as Watched", self)
            mark_action.triggered.connect(lambda: self._mark_video_watched(video, item))
        menu.addAction(mark_action)
        
        # Show menu
        menu.exec(self.video_list.mapToGlobal(position))
        
    def _mark_video_watched(self, video, item):
        """Mark a video as watched."""
        try:
            video.marked_complete = True
            video.watched_percent = 100.0
            self.db_session.commit()
            
            # Update item display
            if isinstance(item, VideoListItem):
                item.update_progress()
                
        except Exception as e:
            logger.exception(f"Error marking video as watched: {e}")
            QMessageBox.warning(self, "Error", f"Failed to mark video as watched: {str(e)}")
            
    def _mark_video_unwatched(self, video, item):
        """Mark a video as unwatched."""
        try:
            video.marked_complete = False
            video.watched_percent = 0.0
            video.watched_position = 0
            self.db_session.commit()
            
            # Update item display
            if isinstance(item, VideoListItem):
                item.update_progress()
                
        except Exception as e:
            logger.exception(f"Error marking video as unwatched: {e}")
            QMessageBox.warning(self, "Error", f"Failed to mark video as unwatched: {str(e)}")
            
    def _on_playlist_context_menu(self, position):
        """Show context menu for playlist items."""
        # Get item at position
        item = self.playlist_list.itemAt(position)
        
        if not item:
            return
            
        playlist_id = item.data(Qt.ItemDataRole.UserRole)
        playlist_title = item.text().split(' (')[0]
        
        # Create context menu
        menu = QMenu(self)
        
        # Add "Delete Playlist" action
        delete_action = QAction(QIcon.fromTheme("edit-delete"), f"Delete Playlist '{playlist_title}'", self)
        delete_action.triggered.connect(lambda: self._on_delete_playlist(playlist_id, item))
        menu.addAction(delete_action)
        
        # Show menu
        menu.exec(self.playlist_list.mapToGlobal(position))

    def _on_delete_playlist(self, playlist_id, item):
        """Handle deletion of a playlist."""
        try:
            # Query playlist from database
            playlist = self.db_session.query(YouTubePlaylist).filter_by(id=playlist_id).first()
            
            if not playlist:
                QMessageBox.warning(self, "Error", "Playlist not found in database.")
                return

            # Confirmation dialog
            reply = QMessageBox.question(
                self, 
                "Confirm Delete", 
                f"Are you sure you want to delete the playlist '{playlist.title}'?\n\n"
                "This will remove the playlist and all its associated video records from Incrementum. "
                "It will NOT delete the playlist from YouTube itself.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                logger.info(f"Deleting playlist ID: {playlist_id}, Title: {playlist.title}")
                
                # Delete associated videos first
                self.db_session.query(YouTubePlaylistVideo).filter_by(playlist_id=playlist_id).delete()
                
                # Delete the playlist itself
                self.db_session.delete(playlist)
                
                # Commit changes
                self.db_session.commit()
                
                logger.info(f"Playlist {playlist_id} deleted successfully.")
                
                # Check if the deleted playlist was the currently selected one
                was_current = (self.current_playlist and self.current_playlist.id == playlist_id)

                # Remove item from the list widget immediately
                self.playlist_list.takeItem(self.playlist_list.row(item))

                # If the deleted playlist was the current one, clear the right panel
                if was_current:
                    self.current_playlist = None
                    self.current_playlist_videos = []
                    self.video_list.clear()
                    self.playlist_info.setText("Select a playlist from the left or import a new one.")
                    logger.info("Cleared right panel as current playlist was deleted.")

                # Update status or show message if needed
                # self.parent().statusBar().showMessage(f"Playlist '{playlist.title}' deleted.", 3000) # If you have access to status bar

        except Exception as e:
            self.db_session.rollback() # Rollback in case of error
            logger.exception(f"Error deleting playlist ID {playlist_id}: {e}")
            QMessageBox.critical(self, "Deletion Error", f"Failed to delete playlist: {str(e)}")

    def _on_import_playlist(self):
        """Handle playlist import button click."""
        from ui.dialogs.import_youtube_playlist_dialog import ImportYouTubePlaylistDialog
        
        dialog = ImportYouTubePlaylistDialog(self.db_session, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Refresh playlist list
            self._load_playlists()
            # Optionally select the newly added playlist if the dialog returns its ID
            new_playlist_id = dialog.get_imported_playlist_id()
            if new_playlist_id:
                self.select_playlist(new_playlist_id)

    def _on_play_all(self):
        """Play all videos in the playlist from the first unwatched video."""
        if not self.current_playlist or not self.current_playlist_videos:
            return
            
        # Find first unwatched video
        for video in self.current_playlist_videos:
            if not video.is_watched:
                self.videoSelected.emit(video.video_id, video.position)
                return
                
        # If all are watched, start from the beginning
        if self.current_playlist_videos:
            first_video = self.current_playlist_videos[0]
            self.videoSelected.emit(first_video.video_id, first_video.position)
            
    def _on_refresh_playlist(self):
        """Refresh the current playlist data from YouTube."""
        if not self.current_playlist:
            return
            
        try:
            # Get playlist ID
            playlist_id = self.current_playlist.playlist_id
            
            # Fetch latest playlist data
            metadata = self.youtube_handler.fetch_playlist_metadata(playlist_id)
            
            if not metadata:
                QMessageBox.warning(self, "Error", "Failed to fetch playlist data from YouTube.")
                return
                
            # Update playlist with new metadata
            self.current_playlist.title = metadata.get('title', self.current_playlist.title)
            self.current_playlist.channel_title = metadata.get('channel_title', self.current_playlist.channel_title)
            self.current_playlist.description = metadata.get('description', self.current_playlist.description)
            self.current_playlist.thumbnail_url = metadata.get('thumbnail_url', self.current_playlist.thumbnail_url)
            self.current_playlist.video_count = metadata.get('video_count', self.current_playlist.video_count)
            self.current_playlist.last_updated = datetime.utcnow()
            
            # Create a dictionary of existing videos by video_id for easy lookup
            existing_videos = {v.video_id: v for v in self.current_playlist_videos}
            
            # Process each video from the API
            position = 1
            for video_data in metadata.get('videos', []):
                video_id = video_data.get('video_id')
                
                if not video_id:
                    continue
                    
                if video_id in existing_videos:
                    # Update existing video
                    video = existing_videos[video_id]
                    video.title = video_data.get('title', video.title)
                    video.position = position
                    video.duration = video_data.get('duration', video.duration)
                else:
                    # Create new video
                    video = YouTubePlaylistVideo(
                        playlist_id=self.current_playlist.id,
                        video_id=video_id,
                        title=video_data.get('title', f'Video {position}'),
                        position=position,
                        duration=video_data.get('duration', 0)
                    )
                    self.db_session.add(video)
                
                position += 1
                
            # Commit changes
            self.db_session.commit()
            
            # Reload the playlist display
            self._update_playlist_info(self.current_playlist)
            self._load_playlist_videos(self.current_playlist)
            
            QMessageBox.information(self, "Success", "Playlist refreshed successfully.")
            
        except Exception as e:
            logger.exception(f"Error refreshing playlist: {e}")
            QMessageBox.warning(self, "Error", f"Failed to refresh playlist: {str(e)}")
            
    # Methods for drag and drop in the knowledge tree
    def get_drag_data(self):
        """Get data for drag operations."""
        if self.current_playlist:
            return {
                'type': 'youtube_playlist',
                'id': self.current_playlist.id,
                'playlist_id': self.current_playlist.playlist_id,
                'title': self.current_playlist.title
            }
        return None

    def select_playlist(self, playlist_id):
        """Select a specific playlist by ID.
        
        Args:
            playlist_id: ID of the playlist to select
        """
        try:
            # Find the playlist item in the list
            for i in range(self.playlist_list.count()):
                item = self.playlist_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == playlist_id:
                    # Select the item
                    self.playlist_list.setCurrentItem(item)
                    # Trigger selection handling
                    self._on_playlist_selected(item)
                    return
                    
            logger.warning(f"Playlist ID {playlist_id} not found in list")
            
        except Exception as e:
            logger.exception(f"Error selecting playlist: {e}")
            # Don't show a message box here to avoid disrupting the UI flow
