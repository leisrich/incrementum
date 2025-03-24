#!/usr/bin/env python3
# ui/Incrementum_configuration.py

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, 
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QComboBox, QTabWidget, QGroupBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
import logging

logger = logging.getLogger(__name__)

class IncrementumConfigurationView(QWidget):
    """
    Configuration view for Incrementum features.
    Allows users to configure algorithm parameters, scheduling options,
    and various settings for the incremental reading and spaced repetition system.
    """
    
    # Signal when settings are changed
    settingsChanged = pyqtSignal()
    
    def __init__(self, settings_manager=None, parent=None):
        """Initialize the configuration view."""
        super().__init__(parent)
        self.settings_manager = settings_manager
        self._init_ui()
        
    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Create tabs for different configuration sections
        tabs = QTabWidget()
        
        # Spaced Repetition tab
        sr_tab = self._create_spaced_repetition_tab()
        tabs.addTab(sr_tab, "Spaced Repetition")
        
        # Queue Management tab
        queue_tab = self._create_queue_tab()
        tabs.addTab(queue_tab, "Queue Management")
        
        # Learning tab
        learning_tab = self._create_learning_tab()
        tabs.addTab(learning_tab, "Learning")
        
        # Add tabs to layout
        layout.addWidget(tabs)
        
        # Add save and reset buttons
        buttons_layout = QHBoxLayout()
        
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        buttons_layout.addWidget(reset_btn)
        
        buttons_layout.addStretch()
        
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save_settings)
        buttons_layout.addWidget(save_btn)
        
        layout.addLayout(buttons_layout)
    
    def _create_spaced_repetition_tab(self):
        """Create the spaced repetition configuration tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # FSRS Algorithm Group
        fsrs_group = QGroupBox("FSRS Algorithm Parameters")
        fsrs_layout = QFormLayout()
        
        # Forgetting index (retention) target
        self.retention_spin = QDoubleSpinBox()
        self.retention_spin.setRange(0.7, 0.99)
        self.retention_spin.setSingleStep(0.01)
        self.retention_spin.setValue(0.9)
        self.retention_spin.setDecimals(2)
        fsrs_layout.addRow("Target Retention Rate:", self.retention_spin)
        
        # Difficulty parameters
        self.difficulty_weight = QDoubleSpinBox()
        self.difficulty_weight.setRange(0.1, 2.0)
        self.difficulty_weight.setSingleStep(0.05)
        self.difficulty_weight.setValue(0.75)
        self.difficulty_weight.setDecimals(2)
        fsrs_layout.addRow("Difficulty Weight (THETA):", self.difficulty_weight)
        
        # Minimum and maximum intervals
        self.min_interval = QSpinBox()
        self.min_interval.setRange(1, 10)
        self.min_interval.setValue(1)
        fsrs_layout.addRow("Minimum Interval (days):", self.min_interval)
        
        self.max_interval = QSpinBox()
        self.max_interval.setRange(365, 36500)
        self.max_interval.setValue(3650)
        self.max_interval.setSingleStep(365)
        fsrs_layout.addRow("Maximum Interval (days):", self.max_interval)
        
        fsrs_group.setLayout(fsrs_layout)
        layout.addWidget(fsrs_group)
        
        # SuperMemo Parameters Group
        sm_group = QGroupBox("SuperMemo Legacy Parameters")
        sm_layout = QFormLayout()
        
        # Interval modifier
        self.interval_modifier = QDoubleSpinBox()
        self.interval_modifier.setRange(0.5, 2.0)
        self.interval_modifier.setSingleStep(0.05)
        self.interval_modifier.setValue(1.0)
        self.interval_modifier.setDecimals(2)
        sm_layout.addRow("Interval Modifier:", self.interval_modifier)
        
        # Initial ease
        self.initial_ease = QDoubleSpinBox()
        self.initial_ease.setRange(1.3, 3.0)
        self.initial_ease.setSingleStep(0.1)
        self.initial_ease.setValue(2.5)
        self.initial_ease.setDecimals(1)
        sm_layout.addRow("Initial Ease Factor:", self.initial_ease)
        
        # Easy bonus
        self.easy_bonus = QDoubleSpinBox()
        self.easy_bonus.setRange(1.0, 2.0)
        self.easy_bonus.setSingleStep(0.05)
        self.easy_bonus.setValue(1.3)
        self.easy_bonus.setDecimals(2)
        sm_layout.addRow("Easy Bonus:", self.easy_bonus)
        
        sm_group.setLayout(sm_layout)
        layout.addWidget(sm_group)
        
        # Add a stretch to push everything up
        layout.addStretch()
        
        return tab
    
    def _create_queue_tab(self):
        """Create the queue management configuration tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Priority Parameters Group
        priority_group = QGroupBox("Queue Priority Parameters")
        priority_layout = QFormLayout()
        
        # Priority weight
        self.priority_weight = QDoubleSpinBox()
        self.priority_weight.setRange(0.0, 1.0)
        self.priority_weight.setSingleStep(0.05)
        self.priority_weight.setValue(0.5)
        self.priority_weight.setDecimals(2)
        priority_layout.addRow("Priority Weight:", self.priority_weight)
        
        # Priority decay
        self.priority_decay = QDoubleSpinBox()
        self.priority_decay.setRange(0.0, 0.1)
        self.priority_decay.setSingleStep(0.01)
        self.priority_decay.setValue(0.01)
        self.priority_decay.setDecimals(3)
        priority_layout.addRow("Priority Decay Rate (per day):", self.priority_decay)
        
        # Priority boosts
        self.highlight_boost = QSpinBox()
        self.highlight_boost.setRange(1, 20)
        self.highlight_boost.setValue(5)
        priority_layout.addRow("Priority Boost for Highlights:", self.highlight_boost)
        
        self.extract_boost = QSpinBox()
        self.extract_boost.setRange(1, 20)
        self.extract_boost.setValue(8)
        priority_layout.addRow("Priority Boost for Extracts:", self.extract_boost)
        
        priority_group.setLayout(priority_layout)
        layout.addWidget(priority_group)
        
        # Queue Options Group
        queue_group = QGroupBox("Queue Options")
        queue_layout = QFormLayout()
        
        # Default queue size
        self.queue_size = QSpinBox()
        self.queue_size.setRange(10, 200)
        self.queue_size.setValue(50)
        self.queue_size.setSingleStep(10)
        queue_layout.addRow("Default Queue Size:", self.queue_size)
        
        # Mix ratio of new vs. due items
        self.new_items_ratio = QSlider(Qt.Orientation.Horizontal)
        self.new_items_ratio.setRange(0, 100)
        self.new_items_ratio.setValue(30)
        self.new_items_ratio.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.new_items_ratio.setTickInterval(10)
        
        ratio_layout = QHBoxLayout()
        ratio_layout.addWidget(QLabel("Due Items"))
        ratio_layout.addWidget(self.new_items_ratio)
        ratio_layout.addWidget(QLabel("New Items"))
        
        queue_layout.addRow("Queue Mix Ratio:", ratio_layout)
        
        queue_group.setLayout(queue_layout)
        layout.addWidget(queue_group)
        
        # Add a stretch to push everything up
        layout.addStretch()
        
        return tab
    
    def _create_learning_tab(self):
        """Create the learning configuration tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Learning Limits Group
        limits_group = QGroupBox("Learning Limits")
        limits_layout = QFormLayout()
        
        # Daily review limits
        self.daily_reviews = QSpinBox()
        self.daily_reviews.setRange(10, 500)
        self.daily_reviews.setValue(100)
        self.daily_reviews.setSingleStep(10)
        limits_layout.addRow("Maximum Daily Reviews:", self.daily_reviews)
        
        # New items per day
        self.new_items_per_day = QSpinBox()
        self.new_items_per_day.setRange(5, 100)
        self.new_items_per_day.setValue(20)
        self.new_items_per_day.setSingleStep(5)
        limits_layout.addRow("New Items Per Day:", self.new_items_per_day)
        
        limits_group.setLayout(limits_layout)
        layout.addWidget(limits_group)
        
        # Learning Features Group
        features_group = QGroupBox("Learning Features")
        features_layout = QFormLayout()
        
        # Enable leech detection
        self.leech_detection = QCheckBox()
        self.leech_detection.setChecked(True)
        features_layout.addRow("Enable Leech Detection:", self.leech_detection)
        
        # Leech threshold
        self.leech_threshold = QSpinBox()
        self.leech_threshold.setRange(3, 10)
        self.leech_threshold.setValue(5)
        features_layout.addRow("Leech Threshold (failures):", self.leech_threshold)
        
        # Enable adaptive learning
        self.adaptive_learning = QCheckBox()
        self.adaptive_learning.setChecked(True)
        features_layout.addRow("Enable Adaptive Learning:", self.adaptive_learning)
        
        features_group.setLayout(features_layout)
        layout.addWidget(features_group)
        
        # Add a stretch to push everything up
        layout.addStretch()
        
        return tab
    
    @pyqtSlot()
    def _reset_defaults(self):
        """Reset all settings to defaults."""
        # FSRS tab
        self.retention_spin.setValue(0.9)
        self.difficulty_weight.setValue(0.75)
        self.min_interval.setValue(1)
        self.max_interval.setValue(3650)
        self.interval_modifier.setValue(1.0)
        self.initial_ease.setValue(2.5)
        self.easy_bonus.setValue(1.3)
        
        # Queue tab
        self.priority_weight.setValue(0.5)
        self.priority_decay.setValue(0.01)
        self.highlight_boost.setValue(5)
        self.extract_boost.setValue(8)
        self.queue_size.setValue(50)
        self.new_items_ratio.setValue(30)
        
        # Learning tab
        self.daily_reviews.setValue(100)
        self.new_items_per_day.setValue(20)
        self.leech_detection.setChecked(True)
        self.leech_threshold.setValue(5)
        self.adaptive_learning.setChecked(True)
        
        logger.info("Reset all settings to defaults")
    
    @pyqtSlot()
    def _save_settings(self):
        """Save settings to configuration."""
        if not self.settings_manager:
            logger.warning("No settings manager available, can't save settings")
            return
        
        # Create a settings dictionary
        settings = {
            # FSRS
            "fsrs": {
                "retention_target": self.retention_spin.value(),
                "difficulty_weight": self.difficulty_weight.value(),
                "min_interval": self.min_interval.value(),
                "max_interval": self.max_interval.value()
            },
            # SuperMemo
            "supermemo": {
                "interval_modifier": self.interval_modifier.value(),
                "initial_ease": self.initial_ease.value(),
                "easy_bonus": self.easy_bonus.value()
            },
            # Queue
            "queue": {
                "priority_weight": self.priority_weight.value(),
                "priority_decay": self.priority_decay.value(),
                "highlight_boost": self.highlight_boost.value(),
                "extract_boost": self.extract_boost.value(),
                "queue_size": self.queue_size.value(),
                "new_items_ratio": self.new_items_ratio.value()
            },
            # Learning
            "learning": {
                "daily_reviews": self.daily_reviews.value(),
                "new_items_per_day": self.new_items_per_day.value(),
                "leech_detection": self.leech_detection.isChecked(),
                "leech_threshold": self.leech_threshold.value(),
                "adaptive_learning": self.adaptive_learning.isChecked()
            }
        }
        
        # Save to settings manager
        self.settings_manager.save_incrementum_settings(settings)
        logger.info("Saved Incrementum configuration settings")
        
        # Emit signal that settings changed
        self.settingsChanged.emit()
    
    def load_settings(self):
        """Load settings from configuration."""
        if not self.settings_manager:
            logger.warning("No settings manager available, using defaults")
            return
        
        # Get settings from manager
        settings = self.settings_manager.get_incrementum_settings()
        if not settings:
            logger.info("No saved settings found, using defaults")
            return
        
        # Load FSRS settings
        fsrs = settings.get("fsrs", {})
        if fsrs:
            self.retention_spin.setValue(fsrs.get("retention_target", 0.9))
            self.difficulty_weight.setValue(fsrs.get("difficulty_weight", 0.75))
            self.min_interval.setValue(fsrs.get("min_interval", 1))
            self.max_interval.setValue(fsrs.get("max_interval", 3650))
        
        # Load SuperMemo settings
        sm = settings.get("supermemo", {})
        if sm:
            self.interval_modifier.setValue(sm.get("interval_modifier", 1.0))
            self.initial_ease.setValue(sm.get("initial_ease", 2.5))
            self.easy_bonus.setValue(sm.get("easy_bonus", 1.3))
        
        # Load Queue settings
        queue = settings.get("queue", {})
        if queue:
            self.priority_weight.setValue(queue.get("priority_weight", 0.5))
            self.priority_decay.setValue(queue.get("priority_decay", 0.01))
            self.highlight_boost.setValue(queue.get("highlight_boost", 5))
            self.extract_boost.setValue(queue.get("extract_boost", 8))
            self.queue_size.setValue(queue.get("queue_size", 50))
            self.new_items_ratio.setValue(queue.get("new_items_ratio", 30))
        
        # Load Learning settings
        learning = settings.get("learning", {})
        if learning:
            self.daily_reviews.setValue(learning.get("daily_reviews", 100))
            self.new_items_per_day.setValue(learning.get("new_items_per_day", 20))
            self.leech_detection.setChecked(learning.get("leech_detection", True))
            self.leech_threshold.setValue(learning.get("leech_threshold", 5))
            self.adaptive_learning.setChecked(learning.get("adaptive_learning", True))
        
        logger.info("Loaded Incrementum configuration settings") 