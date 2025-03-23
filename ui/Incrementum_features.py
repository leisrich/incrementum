#!/usr/bin/env python3
# ui/Incrementum_features.py - UI components for Incrementum-inspired features

import logging
import math
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QComboBox, QSpinBox, QMessageBox, QSlider,
    QGraphicsView, QGraphicsScene, QGraphicsTextItem, QGraphicsLineItem,
    QGraphicsRectItem, QGraphicsPathItem, QTextEdit, QGroupBox, QSplitter, QFormLayout,
    QDoubleSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize, QRectF, QPointF
from PyQt6.QtGui import QFont, QColor, QPainterPath, QPen, QBrush, QPainter

from core.knowledge_base.models import Document, Extract, LearningItem, ReviewHistory
from ui.Incrementum_configuration import IncrementumConfigurationView
from core.spaced_repetition.item_analyzer import ItemQualityAnalyzer, LeechAnalyzer

logger = logging.getLogger(__name__)

class ForgettingCurveVisualizer(QWidget):
    """
    Visualize Incrementum's forgetting curves to help understand memory behavior.
    This shows how memories decay over time and how reviews affect retention.
    """
    
    def __init__(self, db_session, parent=None):
        """Initialize the forgetting curve visualizer."""
        super().__init__(parent)
        self.db_session = db_session
        self.stability_values = [1, 7, 30, 90, 180, 365]  # Days
        
        # Parameters for the forgetting curve
        self.retention_target = 0.9  # Target retention rate (90%)
        self.difficulty = 5.0  # Default difficulty factor
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface."""
        # Main layout
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("Forgetting Curve Simulator")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "This visualization shows how memories decay over time based on the Incrementum algorithm. "
            "The graph displays retrievability (chance of recall) over time for different stability values."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        # Difficulty slider
        controls_layout.addWidget(QLabel("Difficulty:"))
        self.difficulty_slider = QSlider(Qt.Orientation.Horizontal)
        self.difficulty_slider.setRange(1, 10)
        self.difficulty_slider.setValue(5)
        self.difficulty_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.difficulty_slider.setTickInterval(1)
        self.difficulty_slider.valueChanged.connect(self._update_graph)
        controls_layout.addWidget(self.difficulty_slider)
        
        # Retention target
        controls_layout.addWidget(QLabel("Retention Target:"))
        self.retention_combo = QComboBox()
        self.retention_combo.addItems(["70%", "80%", "85%", "90%", "95%"])
        self.retention_combo.setCurrentIndex(3)  # Default to 90%
        self.retention_combo.currentIndexChanged.connect(self._update_graph)
        controls_layout.addWidget(self.retention_combo)
        
        # Add to layout
        layout.addLayout(controls_layout)
        
        # GraphicsView for the graph
        self.view = QGraphicsView()
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)  # Antialiasing
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        layout.addWidget(self.view)
        
        # Create initial graph
        self._update_graph()
    
    @pyqtSlot()
    def _update_graph(self):
        """Update the forgetting curve graph."""
        # Clear existing scene
        self.scene.clear()
        
        # Get parameter values
        self.difficulty = self.difficulty_slider.value()
        retention_str = self.retention_combo.currentText()
        self.retention_target = float(retention_str.strip('%')) / 100.0
        
        # Graph dimensions
        width, height = 800, 400
        margin = 60
        graph_width = width - 2 * margin
        graph_height = height - 2 * margin
        
        # Create coordinate axes
        self._create_axes(margin, width, height, graph_width, graph_height)
        
        # Plot forgetting curves for different stability values
        for stability in self.stability_values:
            color = self._get_color_for_stability(stability)
            curve_path = QPainterPath()
            first_point = True
            
            # Calculate curve points
            for day in range(0, 365, 1):
                # Calculate retrievability: R = e^(-t/S)
                retrievability = math.exp(-day / stability)
                
                # Convert to graph coordinates
                x = margin + (day / 365) * graph_width
                y = margin + (1 - retrievability) * graph_height
                
                if first_point:
                    curve_path.moveTo(x, y)
                    first_point = False
                else:
                    curve_path.lineTo(x, y)
            
            # Create and add path to scene
            curve_item = QGraphicsPathItem(curve_path)
            pen = QPen(color, 2)
            curve_item.setPen(pen)
            self.scene.addItem(curve_item)
            
            # Add label for this curve
            label_x = width - margin
            label_y = margin + (1 - math.exp(-30 / stability)) * graph_height
            label = QGraphicsTextItem(f"S = {stability} days")
            label.setPos(label_x - 100, label_y - 10)
            label.setDefaultTextColor(color)
            self.scene.addItem(label)
        
        # Add optimal intervals for the selected stability values
        self._add_optimal_intervals(margin, graph_width, graph_height)
        
        # Set scene rect and fit view
        self.scene.setSceneRect(0, 0, width, height)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
    
    def _create_axes(self, margin, width, height, graph_width, graph_height):
        """Create coordinate axes for the graph."""
        # X-axis
        x_axis = QGraphicsLineItem(margin, height - margin, width - margin, height - margin)
        self.scene.addItem(x_axis)
        
        # Y-axis
        y_axis = QGraphicsLineItem(margin, margin, margin, height - margin)
        self.scene.addItem(y_axis)
        
        # X-axis labels (days)
        for days in [0, 30, 90, 180, 365]:
            x = margin + (days / 365) * graph_width
            line = QGraphicsLineItem(x, height - margin, x, height - margin + 5)
            self.scene.addItem(line)
            
            label = QGraphicsTextItem(str(days))
            label.setPos(x - 10, height - margin + 10)
            self.scene.addItem(label)
        
        # X-axis title
        x_title = QGraphicsTextItem("Days")
        x_title.setPos(width / 2 - 20, height - 20)
        self.scene.addItem(x_title)
        
        # Y-axis labels (retrievability)
        for r in [0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            y = margin + (1 - r) * graph_height
            line = QGraphicsLineItem(margin - 5, y, margin, y)
            self.scene.addItem(line)
            
            label = QGraphicsTextItem(f"{r:.1f}")
            label.setPos(margin - 30, y - 10)
            self.scene.addItem(label)
        
        # Y-axis title
        y_title = QGraphicsTextItem("Retrievability")
        y_title.setPos(10, margin - 40)
        self.scene.addItem(y_title)
        
        # Add retention target line
        target_y = margin + (1 - self.retention_target) * graph_height
        target_line = QGraphicsLineItem(margin, target_y, width - margin, target_y)
        target_line.setPen(QPen(QColor(255, 0, 0, 100), 1, Qt.PenStyle.DashLine))
        self.scene.addItem(target_line)
        
        target_label = QGraphicsTextItem(f"Target: {self.retention_target:.0%}")
        target_label.setPos(margin + 10, target_y - 20)
        target_label.setDefaultTextColor(QColor(255, 0, 0))
        self.scene.addItem(target_label)
    
    def _add_optimal_intervals(self, margin, graph_width, graph_height):
        """Add markers for optimal intervals based on retention target."""
        for stability in self.stability_values:
            # Calculate optimal interval using retrievability formula: R = e^(-t/S)
            # Solving for t when R = target: t = -S * ln(target)
            optimal_interval = -stability * math.log(self.retention_target)
            
            # Apply difficulty adjustment
            difficulty_factor = math.pow(self.difficulty, -0.75)  # THETA parameter
            optimal_interval *= difficulty_factor
            
            # Don't show if interval is > 365 days
            if optimal_interval > 365:
                continue
                
            # Convert to graph coordinates
            x = margin + (optimal_interval / 365) * graph_width
            y = margin + (1 - self.retention_target) * graph_height
            
            # Draw marker
            marker = QGraphicsRectItem(x - 3, y - 3, 6, 6)
            marker.setBrush(QBrush(QColor(0, 0, 255)))
            self.scene.addItem(marker)
            
            # Add label
            interval_label = QGraphicsTextItem(f"{optimal_interval:.0f} days")
            interval_label.setPos(x + 5, y - 15)
            self.scene.addItem(interval_label)
    
    def _get_color_for_stability(self, stability):
        """Get a color based on stability value."""
        # Colors from blue (short) to red (long)
        if stability <= 1:
            return QColor(50, 50, 255)  # Blue
        elif stability <= 7:
            return QColor(50, 150, 255)  # Light blue
        elif stability <= 30:
            return QColor(50, 200, 50)  # Green
        elif stability <= 90:
            return QColor(200, 200, 50)  # Yellow
        elif stability <= 180:
            return QColor(255, 150, 50)  # Orange
        else:
            return QColor(255, 50, 50)  # Red
    
    def resizeEvent(self, event):
        """Handle resize events to adjust graph scaling."""
        super().resizeEvent(event)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

class IncrementalReadingQueue(QWidget):
    """
    UI component for displaying and managing the incremental reading queue.
    Inspired by Incrementum's reading queue with priority-based scheduling.
    """
    # Signals
    documentSelected = pyqtSignal(int)  # Document ID
    extractSelected = pyqtSignal(int)   # Extract ID
    
    def __init__(self, db_session, parent=None):
        """Initialize the incremental reading queue widget."""
        super().__init__(parent)
        self.db_session = db_session
        self.queue_items = []
        
        self._init_ui()
        
    def _init_ui(self):
        """Initialize the user interface."""
        # Main layout
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("Incremental Reading Queue")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Controls
        controls_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh Queue")
        self.refresh_button.clicked.connect(self.refresh_queue)
        controls_layout.addWidget(self.refresh_button)
        
        # Queue size selector
        self.queue_size_selector = QComboBox()
        self.queue_size_selector.addItems(["10", "20", "50", "100"])
        self.queue_size_selector.setCurrentIndex(1)  # Default to 20
        controls_layout.addWidget(QLabel("Queue Size:"))
        controls_layout.addWidget(self.queue_size_selector)
        
        controls_layout.addStretch()
        layout.addLayout(controls_layout)
        
        # Queue list
        self.queue_list = QListWidget()
        self.queue_list.setAlternatingRowColors(True)
        self.queue_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.queue_list)
        
        # Stats
        self.stats_label = QLabel("Queue Statistics: 0 items (0 documents, 0 extracts)")
        layout.addWidget(self.stats_label)
        
        # Initial load
        self.refresh_queue()
    
    @pyqtSlot()
    def refresh_queue(self):
        """Refresh the incremental reading queue."""
        try:
            # Clear the list
            self.queue_list.clear()
            self.queue_items = []
            
            # Get documents from database
            documents = self.db_session.query(Document).order_by(Document.priority.desc()).limit(10).all()
            for doc in documents:
                self.queue_items.append({
                    'type': 'document',
                    'id': doc.id,
                    'title': doc.title,
                    'priority': doc.priority,
                    'content_type': doc.content_type
                })
                
                # Add to list
                list_item = QListWidgetItem(f"[DOC] {doc.title} ({doc.content_type})")
                list_item.setData(Qt.ItemDataRole.UserRole, {
                    'type': 'document',
                    'id': doc.id
                })
                self.queue_list.addItem(list_item)
            
            # Get extracts from database
            extracts = self.db_session.query(Extract).order_by(Extract.priority.desc()).limit(10).all()
            for extract in extracts:
                content = extract.content[:100] + "..." if len(extract.content) > 100 else extract.content
                self.queue_items.append({
                    'type': 'extract',
                    'id': extract.id,
                    'content': content,
                    'priority': extract.priority,
                    'document_id': extract.document_id
                })
                
                # Add to list
                list_item = QListWidgetItem(f"[EXT] {content}")
                list_item.setData(Qt.ItemDataRole.UserRole, {
                    'type': 'extract',
                    'id': extract.id
                })
                self.queue_list.addItem(list_item)
            
            # Update stats
            self.stats_label.setText(
                f"Queue Statistics: {len(self.queue_items)} items "
                f"({len(documents)} documents, {len(extracts)} extracts)"
            )
            
        except Exception as e:
            logger.error(f"Error refreshing incremental reading queue: {e}")
            QMessageBox.warning(
                self, "Queue Error", 
                f"Error refreshing the queue: {str(e)}"
            )
    
    def _on_item_double_clicked(self, item):
        """Handle double-click on a queue item."""
        item_data = item.data(Qt.ItemDataRole.UserRole)
        
        if item_data['type'] == 'document':
            self.documentSelected.emit(item_data['id'])
        elif item_data['type'] == 'extract':
            self.extractSelected.emit(item_data['id'])

class LeechDetector(QWidget):
    """
    UI component for detecting and managing leeches (difficult items).
    """
    # Signals
    itemSelected = pyqtSignal(int)  # Learning item ID
    
    def __init__(self, db_session, parent=None):
        """Initialize the leech detector widget."""
        super().__init__(parent)
        self.db_session = db_session
        self.leech_items = []
        self.leech_analyzer = LeechAnalyzer(db_session)
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface."""
        # Main layout
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("Leech Detector")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Leeches are items that you repeatedly fail to recall. "
            "These items may need to be rewritten or studied differently."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Settings
        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("Failure Threshold:"))
        
        self.threshold_spinner = QSpinBox()
        self.threshold_spinner.setRange(2, 20)
        self.threshold_spinner.setValue(3)
        settings_layout.addWidget(self.threshold_spinner)
        
        settings_layout.addWidget(QLabel("Failure Rate:"))
        self.failure_rate_spinner = QDoubleSpinBox()
        self.failure_rate_spinner.setRange(0.1, 1.0)
        self.failure_rate_spinner.setSingleStep(0.05)
        self.failure_rate_spinner.setDecimals(2)
        self.failure_rate_spinner.setValue(0.3)
        settings_layout.addWidget(self.failure_rate_spinner)
        
        settings_layout.addWidget(QLabel("Min Reviews:"))
        self.min_reviews_spinner = QSpinBox()
        self.min_reviews_spinner.setRange(1, 10)
        self.min_reviews_spinner.setValue(3)
        settings_layout.addWidget(self.min_reviews_spinner)
        
        self.detect_button = QPushButton("Detect Leeches")
        self.detect_button.clicked.connect(self.detect_leeches)
        settings_layout.addWidget(self.detect_button)
        
        layout.addLayout(settings_layout)
        
        # Splitter for list and details
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.splitter, 1)  # stretch factor 1
        
        # Leech list
        self.leech_list = QListWidget()
        self.leech_list.setAlternatingRowColors(True)
        self.leech_list.itemClicked.connect(self._on_item_clicked)
        self.leech_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.splitter.addWidget(self.leech_list)
        
        # Item details widget
        self.details_group = QGroupBox("Item Details")
        details_layout = QVBoxLayout(self.details_group)
        
        self.item_text_label = QLabel()
        self.item_text_label.setWordWrap(True)
        self.item_text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self.item_text_label)
        
        self.stats_layout = QFormLayout()
        self.review_count_label = QLabel("0")
        self.stats_layout.addRow("Reviews:", self.review_count_label)
        
        self.failure_count_label = QLabel("0")
        self.stats_layout.addRow("Failures:", self.failure_count_label)
        
        self.failure_rate_label = QLabel("0%")
        self.stats_layout.addRow("Failure Rate:", self.failure_rate_label)
        
        self.avg_interval_label = QLabel("0 days")
        self.stats_layout.addRow("Avg Interval:", self.avg_interval_label)
        
        details_layout.addLayout(self.stats_layout)
        
        # Recommendations section
        self.recommendations_label = QLabel("Recommendations:")
        details_layout.addWidget(self.recommendations_label)
        
        self.recommendations_list = QListWidget()
        self.recommendations_list.setMaximumHeight(120)
        details_layout.addWidget(self.recommendations_list)
        
        # Buttons for item actions
        action_layout = QHBoxLayout()
        
        self.rewrite_button = QPushButton("Rewrite Item")
        self.rewrite_button.clicked.connect(self._rewrite_item)
        action_layout.addWidget(self.rewrite_button)
        
        self.reset_button = QPushButton("Reset Progress")
        self.reset_button.clicked.connect(self._reset_item_progress)
        action_layout.addWidget(self.reset_button)
        
        self.dismiss_button = QPushButton("Dismiss as Leech")
        self.dismiss_button.clicked.connect(self._dismiss_leech)
        action_layout.addWidget(self.dismiss_button)
        
        details_layout.addLayout(action_layout)
        
        self.splitter.addWidget(self.details_group)
        
        # Set initial splitter sizes
        self.splitter.setSizes([200, 300])
        
        # Stats summary
        self.stats_label = QLabel("Leeches Found: 0")
        layout.addWidget(self.stats_label)
    
    @pyqtSlot()
    def detect_leeches(self):
        """Detect leech items."""
        try:
            # Clear the list
            self.leech_list.clear()
            self.leech_items = []
            self._clear_details()
            
            # Get parameters
            threshold = self.threshold_spinner.value()
            failure_rate = self.failure_rate_spinner.value()
            min_reviews = self.min_reviews_spinner.value()
            
            # Get leeches using the analyzer
            leeches = self.leech_analyzer.get_leeches(
                threshold=threshold,
                failure_rate_threshold=failure_rate,
                min_reviews=min_reviews
            )
            
            # Store and display results
            for item, stats in leeches:
                self.leech_items.append((item, stats))
                
                # Create a nice display with failure rate and question
                question_preview = item.question[:50] + "..." if len(item.question) > 50 else item.question
                failure_pct = stats['failure_rate'] * 100
                list_text = f"{failure_pct:.1f}% - {question_preview}"
                
                # Add to list
                list_item = QListWidgetItem(list_text)
                list_item.setData(Qt.ItemDataRole.UserRole, item.id)
                self.leech_list.addItem(list_item)
            
            # Update stats
            self.stats_label.setText(f"Leeches Found: {len(self.leech_items)}")
            
        except Exception as e:
            logger.error(f"Error detecting leeches: {e}")
            QMessageBox.warning(
                self, "Leech Detection Error", 
                f"Error detecting leeches: {str(e)}"
            )
    
    def _on_item_clicked(self, item):
        """Handle click on a leech item to show details."""
        item_id = item.data(Qt.ItemDataRole.UserRole)
        
        # Find the item in our list
        for leech_item, stats in self.leech_items:
            if leech_item.id == item_id:
                self._display_item_details(leech_item, stats)
                break
    
    def _on_item_double_clicked(self, item):
        """Handle double-click on a leech item."""
        item_id = item.data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit(item_id)
    
    def _display_item_details(self, item, stats):
        """Display details for the selected leech item."""
        # Set item text
        self.item_text_label.setText(f"Q: {item.question}\nA: {item.answer}")
        
        # Set stats
        self.review_count_label.setText(str(stats['review_count']))
        self.failure_count_label.setText(str(stats['failure_count']))
        
        failure_pct = stats['failure_rate'] * 100
        self.failure_rate_label.setText(f"{failure_pct:.1f}%")
        
        avg_interval = stats['avg_interval']
        self.avg_interval_label.setText(f"{avg_interval:.1f} days")
        
        # Get and display recommendations
        self.recommendations_list.clear()
        recommendations = self.leech_analyzer.get_recommendations(item.id)
        
        for rec in recommendations:
            self.recommendations_list.addItem(rec)
        
        # Enable buttons
        self.rewrite_button.setEnabled(True)
        self.reset_button.setEnabled(True)
        self.dismiss_button.setEnabled(True)
    
    def _clear_details(self):
        """Clear the details panel."""
        self.item_text_label.setText("")
        self.review_count_label.setText("0")
        self.failure_count_label.setText("0")
        self.failure_rate_label.setText("0%")
        self.avg_interval_label.setText("0 days")
        self.recommendations_list.clear()
        
        # Disable buttons
        self.rewrite_button.setEnabled(False)
        self.reset_button.setEnabled(False)
        self.dismiss_button.setEnabled(False)
    
    def _rewrite_item(self):
        """Open the item for rewriting."""
        # Get the currently selected item
        if not self.leech_list.currentItem():
            return
            
        item_id = self.leech_list.currentItem().data(Qt.ItemDataRole.UserRole)
        self.itemSelected.emit(item_id)
    
    def _reset_item_progress(self):
        """Reset the learning progress for the item."""
        if not self.leech_list.currentItem():
            return
            
        item_id = self.leech_list.currentItem().data(Qt.ItemDataRole.UserRole)
        
        try:
            # Delete all review history for this item
            self.db_session.query(ReviewHistory).filter(ReviewHistory.learning_item_id == item_id).delete()
            
            # Update the item's next review date to today
            item = self.db_session.query(LearningItem).filter(LearningItem.id == item_id).one()
            item.next_review_date = datetime.utcnow()
            item.ease_factor = 2.5  # Reset to default
            item.interval = 0
            item.repetitions = 0
            
            self.db_session.commit()
            
            QMessageBox.information(
                self, "Item Reset", 
                "The item's learning progress has been reset successfully."
            )
            
            # Refresh the list
            self.detect_leeches()
            
        except Exception as e:
            logger.error(f"Error resetting item progress: {e}")
            QMessageBox.warning(
                self, "Reset Error", 
                f"Error resetting item progress: {str(e)}"
            )
    
    def _dismiss_leech(self):
        """Mark an item as not a leech (suspended or ignored)."""
        if not self.leech_list.currentItem():
            return
            
        item_id = self.leech_list.currentItem().data(Qt.ItemDataRole.UserRole)
        
        try:
            # Mark the item with a special tag or flag
            item = self.db_session.query(LearningItem).filter(LearningItem.id == item_id).one()
            
            # If the item has notes, append to them, otherwise create new notes
            if item.notes:
                item.notes += "\n[LEECH - Special handling required]"
            else:
                item.notes = "[LEECH - Special handling required]"
            
            # Lower the priority
            item.priority = max(1, item.priority - 20)
            
            self.db_session.commit()
            
            QMessageBox.information(
                self, "Item Dismissed", 
                "The item has been marked as a known leech."
            )
            
            # Remove from the list
            row = self.leech_list.currentRow()
            self.leech_list.takeItem(row)
            if row < len(self.leech_items):
                self.leech_items.pop(row)
            
            # Update stats
            self.stats_label.setText(f"Leeches Found: {len(self.leech_items)}")
            
            # Clear details
            self._clear_details()
            
        except Exception as e:
            logger.error(f"Error dismissing leech: {e}")
            QMessageBox.warning(
                self, "Dismiss Error", 
                f"Error dismissing leech: {str(e)}"
            )

class MinimumInformationEditor(QWidget):
    """
    Editor for creating well-formatted learning items following Incrementum's 20 rules
    of formulating knowledge, which helps create more effective items.
    """
    
    # Signal for when an item is created
    itemCreated = pyqtSignal(int)  # Learning item ID
    
    def __init__(self, db_session, parent=None):
        """Initialize the minimum information editor."""
        super().__init__(parent)
        self.db_session = db_session
        self.quality_analyzer = ItemQualityAnalyzer()
        
        # Rules from Incrementum's 20 rules of formulating knowledge
        self.rules = self.quality_analyzer.rules
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface."""
        # Main layout
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("Incrementum 20 Rules Editor")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Create better learning items using Incrementum's 20 rules of formulating knowledge. "
            "This editor helps you create question-answer pairs that are optimized for memory retention."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Template selection
        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("Template:"))
        
        self.template_combo = QComboBox()
        self.template_combo.addItems([
            "Question → Answer",
            "Cloze deletion",
            "Image occlusion",
            "Definition",
            "Foreign word → Translation"
        ])
        self.template_combo.currentIndexChanged.connect(self._update_template)
        template_layout.addWidget(self.template_combo)
        
        layout.addLayout(template_layout)
        
        # Editor area
        self.editor_layout = QVBoxLayout()
        
        # Question field
        question_layout = QVBoxLayout()
        question_layout.addWidget(QLabel("Question:"))
        self.question_edit = QTextEdit()
        self.question_edit.setMinimumHeight(100)
        question_layout.addWidget(self.question_edit)
        self.editor_layout.addLayout(question_layout)
        
        # Answer field
        answer_layout = QVBoxLayout()
        answer_layout.addWidget(QLabel("Answer:"))
        self.answer_edit = QTextEdit()
        self.answer_edit.setMinimumHeight(100)
        answer_layout.addWidget(self.answer_edit)
        self.editor_layout.addLayout(answer_layout)
        
        # Notes field
        notes_layout = QVBoxLayout()
        notes_layout.addWidget(QLabel("Notes (optional):"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setMinimumHeight(60)
        notes_layout.addWidget(self.notes_edit)
        self.editor_layout.addLayout(notes_layout)
        
        # Priority field
        priority_layout = QHBoxLayout()
        priority_layout.addWidget(QLabel("Priority (1-100):"))
        self.priority_spinner = QSpinBox()
        self.priority_spinner.setRange(1, 100)
        self.priority_spinner.setValue(50)
        priority_layout.addWidget(self.priority_spinner)
        priority_layout.addStretch()
        self.editor_layout.addLayout(priority_layout)
        
        layout.addLayout(self.editor_layout)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.analyze_button = QPushButton("Analyze Quality")
        self.analyze_button.clicked.connect(self._analyze_quality)
        buttons_layout.addWidget(self.analyze_button)
        
        self.create_button = QPushButton("Create Item")
        self.create_button.clicked.connect(self._create_item)
        buttons_layout.addWidget(self.create_button)
        
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear_fields)
        buttons_layout.addWidget(self.clear_button)
        
        layout.addLayout(buttons_layout)
        
        # Quality analysis area
        self.quality_group = QGroupBox("Quality Analysis")
        quality_layout = QVBoxLayout()
        self.quality_text = QLabel("Click 'Analyze Quality' to check your item against Incrementum's 20 rules.")
        self.quality_text.setWordWrap(True)
        quality_layout.addWidget(self.quality_text)
        
        # Quality score
        self.quality_score_label = QLabel("Quality Score: N/A")
        quality_layout.addWidget(self.quality_score_label)
        
        # Recommendations
        self.recommendations_list = QListWidget()
        self.recommendations_list.setMaximumHeight(120)
        quality_layout.addWidget(self.recommendations_list)
        
        self.quality_group.setLayout(quality_layout)
        layout.addWidget(self.quality_group)
        
        # Apply initial template
        self._update_template()
    
    @pyqtSlot(int)
    def _update_template(self):
        """Update the editor template based on selection."""
        template_index = self.template_combo.currentIndex()
        
        if template_index == 0:  # Question → Answer
            self.question_edit.setPlaceholderText("What is the capital of France?")
            self.answer_edit.setPlaceholderText("Paris")
        
        elif template_index == 1:  # Cloze deletion
            self.question_edit.setPlaceholderText("The capital of France is [...]")
            self.answer_edit.setPlaceholderText("Paris")
        
        elif template_index == 2:  # Image occlusion
            self.question_edit.setPlaceholderText("Identify the highlighted part of the image.")
            self.answer_edit.setPlaceholderText("Frontal lobe")
        
        elif template_index == 3:  # Definition
            self.question_edit.setPlaceholderText("Define: Photosynthesis")
            self.answer_edit.setPlaceholderText("The process by which green plants use sunlight to synthesize foods with carbon dioxide and water.")
        
        elif template_index == 4:  # Foreign word
            self.question_edit.setPlaceholderText("French: Bonjour")
            self.answer_edit.setPlaceholderText("Hello")
    
    @pyqtSlot()
    def _analyze_quality(self):
        """Analyze the quality of the item using Incrementum's 20 rules."""
        question = self.question_edit.toPlainText().strip()
        answer = self.answer_edit.toPlainText().strip()
        notes = self.notes_edit.toPlainText().strip()
        
        if not question or not answer:
            QMessageBox.warning(
                self, "Incomplete Item", 
                "Please provide both question and answer."
            )
            return
        
        # Clear previous recommendations
        self.recommendations_list.clear()
        
        # Use the quality analyzer
        analysis = self.quality_analyzer.analyze_quality(question, answer, notes)
        
        # Add violations to the list
        for violation in analysis['violations']:
            item = QListWidgetItem(violation)
            item.setForeground(QColor(255, 0, 0))  # Red text for violations
            self.recommendations_list.addItem(item)
        
        # Add recommendations to the list
        for recommendation in analysis['recommendations']:
            item = QListWidgetItem(recommendation)
            item.setForeground(QColor(0, 0, 255))  # Blue text for recommendations
            self.recommendations_list.addItem(item)
        
        # If no issues found
        if not analysis['violations'] and not analysis['recommendations']:
            self.recommendations_list.addItem("Great job! This item follows the minimum information principle.")
            self.recommendations_list.addItem("Remember to review and refine regularly.")
        
        # Update quality score
        self.quality_score_label.setText(f"Quality Score: {analysis['score']}/100")
        
        # Set color based on score
        if analysis['score'] >= 80:
            self.quality_score_label.setStyleSheet("color: green")
        elif analysis['score'] >= 60:
            self.quality_score_label.setStyleSheet("color: orange")
        else:
            self.quality_score_label.setStyleSheet("color: red")
    
    @pyqtSlot()
    def _create_item(self):
        """Create a new learning item."""
        try:
            question = self.question_edit.toPlainText().strip()
            answer = self.answer_edit.toPlainText().strip()
            notes = self.notes_edit.toPlainText().strip()
            priority = self.priority_spinner.value()
            
            if not question or not answer:
                QMessageBox.warning(
                    self, "Incomplete Item", 
                    "Please provide both question and answer."
                )
                return
            
            # Get extract ID (for now, create a special "Incrementum Editor" extract if needed)
            extract = self._get_or_create_Incrementum_extract()
            
            # Create learning item
            learning_item = LearningItem(
                extract_id=extract.id,
                item_type="qa",  # question-answer format
                question=question,
                answer=answer,
                notes=notes if notes else None,
                priority=priority,
                created_date=datetime.utcnow(),
                modified_date=datetime.utcnow()
            )
            
            self.db_session.add(learning_item)
            self.db_session.commit()
            
            # Emit signal with new item ID
            self.itemCreated.emit(learning_item.id)
            
            # Clear fields
            self._clear_fields()
            
            # Show success message
            QMessageBox.information(
                self, "Success", 
                "Learning item created successfully."
            )
            
        except Exception as e:
            logger.error(f"Error creating learning item: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error creating learning item: {str(e)}"
            )
    
    def _get_or_create_Incrementum_extract(self):
        """Get or create a special extract for Incrementum Editor items."""
        # Look for existing extract
        extract = self.db_session.query(Extract).filter(Extract.title == "Incrementum Editor Items").first()
        
        if not extract:
            # Create a special document for Incrementum items if needed
            document = self.db_session.query(Document).filter(Document.title == "Incrementum Learning Items").first()
            
            if not document:
                document = Document(
                    title="Incrementum Learning Items",
                    author="Incrementum Editor",
                    content_type="system",
                    file_path="system://Incrementum",
                    imported_date=datetime.utcnow(),
                    priority=50
                )
                self.db_session.add(document)
                self.db_session.flush()  # Get ID without committing
            
            # Create extract for Incrementum Editor items
            extract = Extract(
                document_id=document.id,
                title="Incrementum Editor Items",
                content="This extract contains learning items created using the Incrementum 20 Rules Editor.",
                created_date=datetime.utcnow(),
                modified_date=datetime.utcnow(),
                source_page=0,
                priority=50
            )
            self.db_session.add(extract)
            self.db_session.flush()  # Get ID without committing
        
        return extract
    
    @pyqtSlot()
    def _clear_fields(self):
        """Clear all input fields."""
        self.question_edit.clear()
        self.answer_edit.clear()
        self.notes_edit.clear()
        self.priority_spinner.setValue(50)
        self.recommendations_list.clear()
        self.quality_score_label.setText("Quality Score: N/A")
        self.quality_score_label.setStyleSheet("")
    
    def refresh(self):
        """Refresh the editor state."""
        # No specific refresh actions needed for now
        # but this method is needed for consistency with other components
        pass

class IncrementumFeatures(QWidget):
    """
    Main widget for Incrementum-inspired features.
    """
    # Signals
    documentSelected = pyqtSignal(int)  # Document ID
    extractSelected = pyqtSignal(int)   # Extract ID
    learningItemSelected = pyqtSignal(int)  # Learning item ID
    
    def __init__(self, db_session, parent=None):
        """Initialize the Incrementum features widget."""
        super().__init__(parent)
        self.db_session = db_session
        
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface."""
        # Main layout
        layout = QVBoxLayout(self)
        
        # Create tabs
        self.tabs = QTabWidget()
        
        # Incremental Reading Queue
        self.ir_queue = IncrementalReadingQueue(self.db_session)
        self.ir_queue.documentSelected.connect(self.documentSelected)
        self.ir_queue.extractSelected.connect(self.extractSelected)
        self.tabs.addTab(self.ir_queue, "Incremental Reading Queue")
        
        # Leech Detector
        self.leech_detector = LeechDetector(self.db_session)
        self.leech_detector.itemSelected.connect(self.learningItemSelected)
        self.tabs.addTab(self.leech_detector, "Leech Detector")
        
        # Forgetting Curve Visualizer
        self.forgetting_curve = ForgettingCurveVisualizer(self.db_session)
        self.tabs.addTab(self.forgetting_curve, "Forgetting Curves")
        
        # Minimum Information Editor
        self.minimum_information_editor = MinimumInformationEditor(self.db_session)
        self.minimum_information_editor.itemCreated.connect(self.learningItemSelected)
        self.tabs.addTab(self.minimum_information_editor, "Minimum Information Editor")
        
        # Incrementum Configuration 
        self.Incrementum_config = IncrementumConfigurationView(self.db_session)
        self.tabs.addTab(self.Incrementum_config, "SM Algorithm Config")
        
        layout.addWidget(self.tabs)
    
    def refresh(self):
        """Refresh all components."""
        self.ir_queue.refresh_queue()
        self.leech_detector.detect_leeches()
        self.minimum_information_editor.refresh()
        # No need to refresh the forgetting curve or config as they update on demand 