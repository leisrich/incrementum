import os
import logging
from datetime import datetime, timedelta
import json
from typing import List, Dict, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QDialog, QTabWidget, QProgressBar, QSplitter,
    QPushButton, QFrame, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QDateTime
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPainterPath, QLinearGradient

logger = logging.getLogger(__name__)

class ReadingStatsWidget(QWidget):
    """Widget for displaying reading statistics."""
    
    def __init__(self, document_view):
        """Initialize with document view reference."""
        super().__init__()
        self.document_view = document_view
        self.db_session = document_view.db_session
        self.document_id = None
        self.stats = {}
        self._create_ui()
        
        # Connect stats update signal if available
        if hasattr(document_view, 'position_manager') and hasattr(document_view.position_manager, 'readingStatsUpdated'):
            document_view.position_manager.readingStatsUpdated.connect(self._update_stats)
    
    def _create_ui(self):
        """Create the UI components."""
        layout = QVBoxLayout()
        
        # Progress section
        progress_frame = QFrame()
        progress_frame.setFrameShape(QFrame.Shape.StyledPanel)
        progress_layout = QVBoxLayout(progress_frame)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% read")
        progress_layout.addWidget(self.progress_bar)
        
        # Progress details
        progress_details = QHBoxLayout()
        
        self.position_label = QLabel("Position: 0")
        progress_details.addWidget(self.position_label)
        
        progress_details.addStretch(1)
        
        self.remaining_label = QLabel("Remaining: Unknown")
        progress_details.addWidget(self.remaining_label)
        
        progress_layout.addLayout(progress_details)
        
        # Add to main layout
        layout.addWidget(progress_frame)
        
        # Session info
        session_frame = QFrame()
        session_frame.setFrameShape(QFrame.Shape.StyledPanel)
        session_layout = QVBoxLayout(session_frame)
        
        session_layout.addWidget(QLabel("<b>Current Session</b>"))
        
        # Session details
        session_grid = QHBoxLayout()
        
        # Session time
        session_time_layout = QVBoxLayout()
        session_time_layout.addWidget(QLabel("Reading Time:"))
        self.session_time_label = QLabel("0 minutes")
        self.session_time_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.session_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        session_time_layout.addWidget(self.session_time_label)
        session_grid.addLayout(session_time_layout)
        
        # Reading speed
        speed_layout = QVBoxLayout()
        speed_layout.addWidget(QLabel("Reading Speed:"))
        self.speed_label = QLabel("0 units/min")
        self.speed_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        speed_layout.addWidget(self.speed_label)
        session_grid.addLayout(speed_layout)
        
        session_layout.addLayout(session_grid)
        
        # Reading progress
        self.reading_estimate = QLabel("Estimated finish: Unknown")
        session_layout.addWidget(self.reading_estimate)
        
        # Add to main layout
        layout.addWidget(session_frame)
        
        # Reading history visualization
        self.history_view = ReadingHistoryView(self.document_view)
        self.history_view.setMinimumHeight(100)
        layout.addWidget(self.history_view)
        
        # Add total reading time
        self.total_time_label = QLabel("Total Reading Time: 0 minutes")
        layout.addWidget(self.total_time_label)
        
        # Add stretch to push everything to the top
        layout.addStretch(1)
        
        # Set layout
        self.setLayout(layout)
        
        # Update timer for session time
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_session_time)
        self.update_timer.start(10000)  # Update every 10 seconds
    
    def set_document(self, document_id):
        """Set the current document."""
        self.document_id = document_id
        self._load_stats()
        self.history_view.set_document(document_id)
    
    def _load_stats(self):
        """Load reading statistics for the current document."""
        if not self.document_id:
            return
            
        try:
            from core.knowledge_base.models import Document
            
            document = self.db_session.query(Document).get(self.document_id)
            if not document:
                return
                
            # Get extra info
            extra_info = {}
            if hasattr(document, 'extra_info') and document.extra_info:
                try:
                    extra_info = json.loads(document.extra_info)
                except:
                    extra_info = {}
            
            # Get reading stats
            reading_stats = extra_info.get('reading_stats', {})
            
            # Update display
            self._update_stats_display(reading_stats)
                
        except Exception as e:
            logger.exception(f"Error loading reading stats: {e}")
    
    def _update_stats(self, stats):
        """Update statistics from position manager."""
        self.stats = stats
        
        # Update progress
        if 'progress_percent' in stats:
            self.progress_bar.setValue(int(stats['progress_percent']))
        
        if 'current_position' in stats:
            self.position_label.setText(f"Position: {stats['current_position']:.0f}")
        
        # Update remaining info
        if 'document_length' in stats and 'current_position' in stats:
            remaining = stats['document_length'] - stats['current_position']
            if 'reading_speed' in stats and stats['reading_speed'] > 0:
                # Calculate remaining time
                seconds_remaining = remaining / stats['reading_speed']
                
                minutes = int(seconds_remaining / 60)
                
                if minutes < 60:
                    self.remaining_label.setText(f"Remaining: ~{minutes} min")
                else:
                    hours = minutes / 60
                    self.remaining_label.setText(f"Remaining: ~{hours:.1f} hrs")
            else:
                self.remaining_label.setText(f"Remaining: {remaining:.0f} units")
        
        # Update reading speed
        if 'reading_speed' in stats and stats['reading_speed'] > 0:
            speed = stats['reading_speed'] * 60  # Convert to per minute
            self.speed_label.setText(f"{speed:.1f} units/min")
        
        # Update session time
        if 'current_session_duration' in stats:
            minutes = int(stats['current_session_duration'] / 60)
            
            if minutes < 60:
                self.session_time_label.setText(f"{minutes} minutes")
            else:
                hours = minutes / 60
                self.session_time_label.setText(f"{hours:.1f} hours")
        
        # Update total reading time
        if 'total_reading_time' in stats:
            minutes = int(stats['total_reading_time'] / 60)
            
            if minutes < 60:
                self.total_time_label.setText(f"Total Reading Time: {minutes} minutes")
            else:
                hours = minutes / 60
                self.total_time_label.setText(f"Total Reading Time: {hours:.1f} hours")
        
        # Update estimated completion
        if 'estimated_completion' in stats:
            try:
                completion_time = datetime.fromisoformat(stats['estimated_completion'])
                now = datetime.utcnow()
                
                # Format based on how far in the future
                if completion_time - now < timedelta(hours=1):
                    # Less than an hour
                    minutes = int((completion_time - now).total_seconds() / 60)
                    self.reading_estimate.setText(f"Estimated finish: In {minutes} minutes")
                elif completion_time - now < timedelta(days=1):
                    # Less than a day
                    completion_local = completion_time.astimezone()
                    time_str = completion_local.strftime("%I:%M %p")
                    self.reading_estimate.setText(f"Estimated finish: Today at {time_str}")
                else:
                    # More than a day
                    completion_local = completion_time.astimezone()
                    date_str = completion_local.strftime("%b %d at %I:%M %p")
                    self.reading_estimate.setText(f"Estimated finish: {date_str}")
            except Exception as e:
                logger.error(f"Error formatting estimated completion: {e}")
                self.reading_estimate.setText(f"Estimated finish: Unknown")
        else:
            self.reading_estimate.setText(f"Estimated finish: Unknown")
    
    def _update_stats_display(self, reading_stats):
        """Update display with reading statistics."""
        # Update total time
        total_time = reading_stats.get('total_time', 0)
        minutes = int(total_time / 60)
        
        if minutes < 60:
            self.total_time_label.setText(f"Total Reading Time: {minutes} minutes")
        else:
            hours = minutes / 60
            self.total_time_label.setText(f"Total Reading Time: {hours:.1f} hours")
        
        # Update history view
        self.history_view.update_sessions(reading_stats.get('sessions', []))
    
    def _update_session_time(self):
        """Update session time display."""
        if 'current_session_duration' in self.stats:
            # Add 10 seconds (update interval)
            self.stats['current_session_duration'] += 10
            
            minutes = int(self.stats['current_session_duration'] / 60)
            
            if minutes < 60:
                self.session_time_label.setText(f"{minutes} minutes")
            else:
                hours = minutes / 60
                self.session_time_label.setText(f"{hours:.1f} hours")


class ReadingHistoryView(QWidget):
    """Widget for visualizing reading history."""
    
    def __init__(self, document_view):
        """Initialize with document view reference."""
        super().__init__()
        self.document_view = document_view
        self.db_session = document_view.db_session
        self.document_id = None
        self.sessions = []
        self.time_range = 7  # Days to display
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(80)
    
    def set_document(self, document_id):
        """Set the current document."""
        self.document_id = document_id
        self._load_sessions()
    
    def _load_sessions(self):
        """Load reading sessions for visualization."""
        if not self.document_id:
            return
            
        try:
            from core.knowledge_base.models import Document
            
            document = self.db_session.query(Document).get(self.document_id)
            if not document:
                return
                
            # Get extra info
            extra_info = {}
            if hasattr(document, 'extra_info') and document.extra_info:
                try:
                    extra_info = json.loads(document.extra_info)
                except:
                    extra_info = {}
            
            # Get reading stats
            reading_stats = extra_info.get('reading_stats', {})
            
            # Get sessions
            self.sessions = reading_stats.get('sessions', [])
            
            # Update display
            self.update()
                
        except Exception as e:
            logger.exception(f"Error loading reading sessions: {e}")
    
    def update_sessions(self, sessions):
        """Update with new sessions data."""
        self.sessions = sessions
        self.update()
    
    def paintEvent(self, event):
        """Paint the reading history visualization."""
        if not self.sessions:
            # Draw "No reading history" message
            painter = QPainter(self)
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(
                self.rect(), 
                Qt.AlignmentFlag.AlignCenter, 
                "No reading history available"
            )
            return
            
        # Set up painter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate time bounds
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=self.time_range)
        
        # Filter sessions in time range
        visible_sessions = []
        for session in self.sessions:
            try:
                session_end = datetime.fromisoformat(session['end_time'])
                if session_end >= start_time:
                    visible_sessions.append(session)
            except (KeyError, ValueError):
                continue
        
        if not visible_sessions:
            # Draw "No recent reading history" message
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(
                self.rect(), 
                Qt.AlignmentFlag.AlignCenter, 
                f"No reading history in the last {self.time_range} days"
            )
            return
        
        # Draw time axis
        self._draw_time_axis(painter, start_time, end_time)
        
        # Draw sessions
        self._draw_sessions(painter, visible_sessions, start_time, end_time)
    
    def _draw_time_axis(self, painter, start_time, end_time):
        """Draw the time axis with day markers."""
        # Draw axis line
        painter.setPen(QPen(Qt.GlobalColor.gray, 1))
        
        # Calculate axis position
        axis_y = self.height() - 20
        
        # Draw axis line
        painter.drawLine(10, axis_y, self.width() - 10, axis_y)
        
        # Calculate day markers
        current_day = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = end_time.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Draw day markers
        while current_day <= end_day:
            # Calculate x position
            time_range = (end_time - start_time).total_seconds()
            position = (current_day - start_time).total_seconds() / time_range
            x = 10 + position * (self.width() - 20)
            
            # Draw tick
            painter.drawLine(int(x), axis_y, int(x), axis_y + 5)
            
            # Draw date label for every other day
            if current_day.day % 2 == 0:
                date_str = current_day.strftime("%m/%d")
                
                # Draw text
                painter.drawText(
                    int(x - 15), axis_y + 15, 
                    30, 15, 
                    Qt.AlignmentFlag.AlignCenter, 
                    date_str
                )
            
            # Move to next day
            current_day += timedelta(days=1)
    
    def _draw_sessions(self, painter, sessions, start_time, end_time):
        """Draw reading sessions on the time axis."""
        # Calculate time range in seconds
        time_range = (end_time - start_time).total_seconds()
        
        # Calculate max duration for height scaling
        max_duration = 0
        for session in sessions:
            try:
                if 'duration' in session:
                    max_duration = max(max_duration, session['duration'])
                else:
                    session_start = datetime.fromisoformat(session['start_time'])
                    session_end = datetime.fromisoformat(session['end_time'])
                    duration = (session_end - session_start).total_seconds()
                    max_duration = max(max_duration, duration)
            except (KeyError, ValueError):
                continue
        
        # Ensure max_duration is not zero
        if max_duration <= 0:
            max_duration = 3600  # Default to 1 hour
        
        # Maximum bar height
        max_height = self.height() - 30
        
        # Draw bars for each session
        for session in sessions:
            try:
                # Get session times
                session_start = datetime.fromisoformat(session['start_time'])
                session_end = datetime.fromisoformat(session['end_time'])
                
                # Calculate duration
                duration = (session_end - session_start).total_seconds()
                
                # Skip very short sessions
                if duration < 60:  # Less than a minute
                    continue
                
                # Calculate position and width
                start_pos = (session_start - start_time).total_seconds() / time_range
                end_pos = (session_end - start_time).total_seconds() / time_range
                
                x1 = 10 + start_pos * (self.width() - 20)
                x2 = 10 + end_pos * (self.width() - 20)
                
                # Calculate bar height based on duration
                height = min(max_height, (duration / max_duration) * max_height)
                
                # Calculate bar position
                y = self.height() - 25 - height
                
                # Create gradient fill
                gradient = QLinearGradient(x1, y, x1, y + height)
                gradient.setColorAt(0, QColor(0, 120, 255, 180))
                gradient.setColorAt(1, QColor(0, 80, 255, 120))
                
                # Draw bar
                painter.setBrush(QBrush(gradient))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRoundedRect(int(x1), int(y), max(2, int(x2 - x1)), int(height), 2, 2)
                
                # Draw outline
                painter.setPen(QPen(QColor(0, 100, 200, 180), 1))
                painter.drawRoundedRect(int(x1), int(y), max(2, int(x2 - x1)), int(height), 2, 2)
                
                # Draw duration label for longer sessions
                if x2 - x1 > 40:  # Only if there's enough space
                    minutes = int(duration / 60)
                    time_str = f"{minutes}m"
                    
                    if minutes >= 60:
                        hours = minutes / 60
                        time_str = f"{hours:.1f}h"
                    
                    # Draw text
                    painter.setPen(Qt.GlobalColor.white)
                    painter.drawText(
                        int(x1), int(y), 
                        int(x2 - x1), int(height), 
                        Qt.AlignmentFlag.AlignCenter, 
                        time_str
                    )
            except (KeyError, ValueError, Exception) as e:
                logger.error(f"Error drawing session: {e}")
                continue
    
    def mousePressEvent(self, event):
        """Handle mouse press events."""
        # Future enhancement: add interaction with the visualization
        super().mousePressEvent(event)


class ReadingStatsDialog(QDialog):
    """Dialog for displaying detailed reading statistics."""
    
    def __init__(self, document_view, parent=None):
        """Initialize with document view reference."""
        super().__init__(parent)
        self.document_view = document_view
        self.db_session = document_view.db_session
        self.document_id = document_view.document_id if hasattr(document_view, 'document_id') else None
        self._create_ui()
        
        # Load data if document ID is available
        if self.document_id:
            self.load_document(self.document_id)
    
    def _create_ui(self):
        """Create the UI components."""
        self.setWindowTitle("Reading Statistics")
        self.resize(600, 500)
        
        layout = QVBoxLayout()
        
        # Tabs
        tabs = QTabWidget()
        
        # Overview tab
        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        
        # Reading progress
        self.stats_widget = ReadingStatsWidget(self.document_view)
        overview_layout.addWidget(self.stats_widget)
        
        tabs.addTab(overview_tab, "Overview")
        
        # Sessions tab
        sessions_tab = QWidget()
        sessions_layout = QVBoxLayout(sessions_tab)
        
        # Sessions table
        self.sessions_table = QTableWidget()
        self.sessions_table.setColumnCount(4)
        self.sessions_table.setHorizontalHeaderLabels(["Date", "Duration", "Progress", "Position"])
        self.sessions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        sessions_layout.addWidget(self.sessions_table)
        
        tabs.addTab(sessions_tab, "Sessions")
        
        # Reading habits tab
        habits_tab = QWidget()
        habits_layout = QVBoxLayout(habits_tab)
        
        # Time of day chart
        time_chart_label = QLabel("Reading Times")
        time_chart_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        habits_layout.addWidget(time_chart_label)
        
        self.time_chart = TimeOfDayChart()
        habits_layout.addWidget(self.time_chart)
        
        # Day of week chart
        day_chart_label = QLabel("Reading Days")
        day_chart_label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        habits_layout.addWidget(day_chart_label)
        
        self.day_chart = DayOfWeekChart()
        habits_layout.addWidget(self.day_chart)
        
        tabs.addTab(habits_tab, "Habits")
        
        # Add tabs to layout
        layout.addWidget(tabs)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_data)
        button_layout.addWidget(refresh_button)
        
        button_layout.addStretch(1)
        
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_document(self, document_id):
        """Load data for the specified document."""
        self.document_id = document_id
        self.stats_widget.set_document(document_id)
        self._load_sessions()
        self._analyze_reading_habits()
    
    def _refresh_data(self):
        """Refresh all data."""
        if self.document_id:
            self.load_document(self.document_id)
    
    def _load_sessions(self):
        """Load reading sessions into the sessions table."""
        if not self.document_id:
            return
            
        try:
            from core.knowledge_base.models import Document
            
            document = self.db_session.query(Document).get(self.document_id)
            if not document:
                return
                
            # Get extra info
            extra_info = {}
            if hasattr(document, 'extra_info') and document.extra_info:
                try:
                    extra_info = json.loads(document.extra_info)
                except:
                    extra_info = {}
            
            # Get reading stats
            reading_stats = extra_info.get('reading_stats', {})
            
            # Get sessions
            sessions = reading_stats.get('sessions', [])
            
            # Clear table
            self.sessions_table.setRowCount(0)
            
            # Add sessions in reverse order (newest first)
            for i, session in enumerate(reversed(sessions)):
                try:
                    # Get session data
                    start_time = datetime.fromisoformat(session['start_time'])
                    end_time = datetime.fromisoformat(session['end_time'])
                    
                    # Calculate duration
                    duration = (end_time - start_time).total_seconds()
                    duration_str = f"{int(duration / 60)} min"
                    
                    if duration >= 3600:
                        hours = duration / 3600
                        duration_str = f"{hours:.1f} hours"
                    
                    # Calculate progress if available
                    progress_str = "N/A"
                    if 'start_position' in session and 'end_position' in session:
                        progress = session['end_position'] - session['start_position']
                        progress_str = f"{progress:.0f} units"
                    
                    # Format date/time
                    date_str = start_time.strftime("%Y-%m-%d %H:%M")
                    
                    # Position
                    position_str = f"{session.get('end_position', 0):.0f}"
                    
                    # Add row
                    self.sessions_table.insertRow(i)
                    self.sessions_table.setItem(i, 0, QTableWidgetItem(date_str))
                    self.sessions_table.setItem(i, 1, QTableWidgetItem(duration_str))
                    self.sessions_table.setItem(i, 2, QTableWidgetItem(progress_str))
                    self.sessions_table.setItem(i, 3, QTableWidgetItem(position_str))
                    
                except (KeyError, ValueError, Exception) as e:
                    logger.error(f"Error loading session: {e}")
                    continue
                
        except Exception as e:
            logger.exception(f"Error loading sessions: {e}")
    
    def _analyze_reading_habits(self):
        """Analyze reading habits for visualization."""
        if not self.document_id:
            return
            
        try:
            from core.knowledge_base.models import Document
            
            document = self.db_session.query(Document).get(self.document_id)
            if not document:
                return
                
            # Get extra info
            extra_info = {}
            if hasattr(document, 'extra_info') and document.extra_info:
                try:
                    extra_info = json.loads(document.extra_info)
                except:
                    extra_info = {}
            
            # Get reading stats
            reading_stats = extra_info.get('reading_stats', {})
            
            # Get sessions
            sessions = reading_stats.get('sessions', [])
            
            # Analyze time of day
            hours_data = [0] * 24  # 24 hours
            
            # Analyze day of week
            days_data = [0] * 7  # 7 days
            
            # Process sessions
            for session in sessions:
                try:
                    # Get session times
                    start_time = datetime.fromisoformat(session['start_time'])
                    end_time = datetime.fromisoformat(session['end_time'])
                    
                    # Calculate duration
                    duration = (end_time - start_time).total_seconds() / 60  # Minutes
                    
                    # Add to time of day data
                    hour = start_time.hour
                    hours_data[hour] += duration
                    
                    # Add to day of week data
                    day = start_time.weekday()
                    days_data[day] += duration
                    
                except (KeyError, ValueError, Exception) as e:
                    logger.error(f"Error analyzing session: {e}")
                    continue
            
            # Update charts
            self.time_chart.update_data(hours_data)
            self.day_chart.update_data(days_data)
                
        except Exception as e:
            logger.exception(f"Error analyzing reading habits: {e}")


class TimeOfDayChart(QWidget):
    """Chart showing reading time by hour of day."""
    
    def __init__(self):
        """Initialize the chart."""
        super().__init__()
        self.hours_data = [0] * 24
        self.max_value = 1
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(150)
    
    def update_data(self, hours_data):
        """Update with new data."""
        self.hours_data = hours_data
        self.max_value = max(max(hours_data), 1)  # Ensure non-zero
        self.update()
    
    def paintEvent(self, event):
        """Paint the chart."""
        # Set up painter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate dimensions
        chart_width = self.width() - 40  # Margins
        chart_height = self.height() - 40
        bar_width = chart_width / 24
        
        # Draw axes
        painter.setPen(QPen(Qt.GlobalColor.gray, 1))
        
        # X-axis
        x_axis_y = self.height() - 20
        painter.drawLine(20, x_axis_y, self.width() - 20, x_axis_y)
        
        # Y-axis
        painter.drawLine(20, 20, 20, x_axis_y)
        
        # Draw hour labels and gridlines
        for i in range(0, 24, 3):  # Every 3 hours
            x = 20 + i * bar_width
            
            # Draw tick
            painter.drawLine(int(x), x_axis_y, int(x), x_axis_y + 5)
            
            # Draw label
            hour_str = f"{i:02d}"
            painter.drawText(
                int(x - 10), x_axis_y + 15, 
                20, 15, 
                Qt.AlignmentFlag.AlignCenter, 
                hour_str
            )
            
            # Draw gridline
            painter.setPen(QPen(QColor(200, 200, 200, 100), 1, Qt.PenStyle.DotLine))
            painter.drawLine(int(x), 20, int(x), x_axis_y)
            painter.setPen(QPen(Qt.GlobalColor.gray, 1))
        
        # Draw bars
        for i, value in enumerate(self.hours_data):
            if value <= 0:
                continue
                
            # Calculate bar position and size
            x = 20 + i * bar_width
            bar_height = (value / self.max_value) * chart_height
            y = x_axis_y - bar_height
            
            # Create gradient fill
            gradient = QLinearGradient(x, y, x, x_axis_y)
            
            # Color based on time of day
            if i < 6:  # Night (midnight to 6am)
                gradient.setColorAt(0, QColor(100, 100, 255, 180))
                gradient.setColorAt(1, QColor(70, 70, 200, 120))
            elif i < 12:  # Morning (6am to noon)
                gradient.setColorAt(0, QColor(255, 200, 100, 180))
                gradient.setColorAt(1, QColor(255, 170, 50, 120))
            elif i < 18:  # Afternoon (noon to 6pm)
                gradient.setColorAt(0, QColor(255, 150, 100, 180))
                gradient.setColorAt(1, QColor(255, 120, 50, 120))
            else:  # Evening (6pm to midnight)
                gradient.setColorAt(0, QColor(150, 100, 255, 180))
                gradient.setColorAt(1, QColor(120, 70, 200, 120))
            
            # Draw bar
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                int(x), int(y), 
                max(1, int(bar_width - 2)), int(bar_height), 
                2, 2
            )
            
            # Draw outline
            painter.setPen(QPen(QColor(100, 100, 150, 120), 1))
            painter.drawRoundedRect(
                int(x), int(y), 
                max(1, int(bar_width - 2)), int(bar_height), 
                2, 2
            )
            
            # Draw value label for larger bars
            if bar_height > 20:
                minutes = int(value)
                time_str = f"{minutes}m"
                
                if minutes >= 60:
                    hours = minutes / 60
                    time_str = f"{hours:.1f}h"
                
                painter.setPen(QColor(50, 50, 50, 200))
                painter.drawText(
                    int(x), int(y - 15), 
                    int(bar_width), 15, 
                    Qt.AlignmentFlag.AlignCenter, 
                    time_str
                )


class DayOfWeekChart(QWidget):
    """Chart showing reading time by day of week."""
    
    def __init__(self):
        """Initialize the chart."""
        super().__init__()
        self.days_data = [0] * 7
        self.max_value = 1
        self.day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(150)
    
    def update_data(self, days_data):
        """Update with new data."""
        self.days_data = days_data
        self.max_value = max(max(days_data), 1)  # Ensure non-zero
        self.update()
    
    def paintEvent(self, event):
        """Paint the chart."""
        # Set up painter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate dimensions
        chart_width = self.width() - 40  # Margins
        chart_height = self.height() - 40
        bar_width = chart_width / 7
        
        # Draw axes
        painter.setPen(QPen(Qt.GlobalColor.gray, 1))
        
        # X-axis
        x_axis_y = self.height() - 20
        painter.drawLine(20, x_axis_y, self.width() - 20, x_axis_y)
        
        # Y-axis
        painter.drawLine(20, 20, 20, x_axis_y)
        
        # Draw day labels and gridlines
        for i in range(7):
            x = 20 + i * bar_width + bar_width/2
            
            # Draw tick
            painter.drawLine(int(x), x_axis_y, int(x), x_axis_y + 5)
            
            # Draw label
            day_str = self.day_names[i]
            painter.drawText(
                int(x - 15), x_axis_y + 15, 
                30, 15, 
                Qt.AlignmentFlag.AlignCenter, 
                day_str
            )
            
            # Draw gridline
            painter.setPen(QPen(QColor(200, 200, 200, 100), 1, Qt.PenStyle.DotLine))
            painter.drawLine(int(x), 20, int(x), x_axis_y)
            painter.setPen(QPen(Qt.GlobalColor.gray, 1))
        
        # Draw bars
        for i, value in enumerate(self.days_data):
            if value <= 0:
                continue
                
            # Calculate bar position and size
            x = 20 + i * bar_width + 5  # Add padding
            bar_width_actual = bar_width - 10  # Subtract padding
            bar_height = (value / self.max_value) * chart_height
            y = x_axis_y - bar_height
            
            # Create gradient fill
            gradient = QLinearGradient(x, y, x, x_axis_y)
            
            # Color based on weekday/weekend
            if i < 5:  # Weekday
                gradient.setColorAt(0, QColor(100, 200, 100, 180))
                gradient.setColorAt(1, QColor(70, 170, 70, 120))
            else:  # Weekend
                gradient.setColorAt(0, QColor(200, 100, 100, 180))
                gradient.setColorAt(1, QColor(170, 70, 70, 120))
            
            # Draw bar
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(
                int(x), int(y), 
                max(1, int(bar_width_actual)), int(bar_height), 
                3, 3
            )
            
            # Draw outline
            painter.setPen(QPen(QColor(100, 100, 100, 120), 1))
            painter.drawRoundedRect(
                int(x), int(y), 
                max(1, int(bar_width_actual)), int(bar_height), 
                3, 3
            )
            
            # Draw value label
            minutes = int(value)
            time_str = f"{minutes}m"
            
            if minutes >= 60:
                hours = minutes / 60
                time_str = f"{hours:.1f}h"
            
            painter.setPen(QColor(50, 50, 50, 200))
            painter.drawText(
                int(x), int(y - 15), 
                int(bar_width_actual), 15, 
                Qt.AlignmentFlag.AlignCenter, 
                time_str
            )
