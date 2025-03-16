# ui/settings_dialog.py

import os
import logging
from typing import Dict, Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTabWidget, QWidget, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QColorDialog, QFileDialog, QGroupBox,
    QMessageBox, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSettings
from PyQt6.QtGui import QColor, QFont

from core.utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class SettingsDialog(QDialog):
    """Dialog for editing application settings."""
    
    settingsChanged = pyqtSignal()
    
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        
        self.settings_manager = settings_manager
        
        # Create UI
        self._create_ui()
        
        # Load settings
        self._load_settings()
    
    def _create_ui(self):
        """Create the UI layout."""
        self.setWindowTitle("Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        
        main_layout = QVBoxLayout(self)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Add tabs
        self._create_general_tab()
        self._create_ui_tab()
        self._create_document_tab()
        self._create_learning_tab()
        self._create_algorithm_tab()
        self._create_backup_tab()
        self._create_advanced_tab()
        
        main_layout.addWidget(self.tab_widget)
        
        # Add buttons
        button_layout = QHBoxLayout()
        
        # Import/Export buttons
        import_button = QPushButton("Import Settings")
        import_button.clicked.connect(self._on_import_settings)
        button_layout.addWidget(import_button)
        
        export_button = QPushButton("Export Settings")
        export_button.clicked.connect(self._on_export_settings)
        button_layout.addWidget(export_button)
        
        button_layout.addStretch()
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel | 
            QDialogButtonBox.StandardButton.Apply |
            QDialogButtonBox.StandardButton.Reset
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._on_apply)
        button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self._on_reset)
        
        button_layout.addWidget(button_box)
        
        main_layout.addLayout(button_layout)
    
    def _create_general_tab(self):
        """Create the General settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Auto-save interval
        self.auto_save_interval = QSpinBox()
        self.auto_save_interval.setRange(1, 60)
        self.auto_save_interval.setSuffix(" minutes")
        layout.addRow("Auto-save interval:", self.auto_save_interval)
        
        # Max recent documents
        self.max_recent_documents = QSpinBox()
        self.max_recent_documents.setRange(1, 50)
        layout.addRow("Maximum recent documents:", self.max_recent_documents)
        
        # Default category
        self.default_category = QComboBox()
        self.default_category.addItem("None", None)
        # Populate categories from database - this would be done in a real implementation
        # For now just add a placeholder
        self.default_category.addItem("General", 1)
        layout.addRow("Default category:", self.default_category)
        
        # Show statistics on startup
        self.startup_show_statistics = QCheckBox()
        layout.addRow("Show statistics on startup:", self.startup_show_statistics)
        
        # Add tab
        self.tab_widget.addTab(tab, "General")
    
    def _create_ui_tab(self):
        """Create the UI settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        layout.addRow("Theme:", self.theme_combo)
        
        # Font family
        self.font_family = QComboBox()
        self.font_family.addItems(["Arial", "Times New Roman", "Courier New", "Verdana", "System"])
        layout.addRow("Font family:", self.font_family)
        
        # Font size
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        layout.addRow("Font size:", self.font_size)
        
        # Show category panel
        self.show_category_panel = QCheckBox()
        layout.addRow("Show category panel:", self.show_category_panel)
        
        # Default split ratio
        self.default_split_ratio = QDoubleSpinBox()
        self.default_split_ratio.setRange(0.1, 0.5)
        self.default_split_ratio.setSingleStep(0.05)
        layout.addRow("Default split ratio:", self.default_split_ratio)
        
        # Add tab
        self.tab_widget.addTab(tab, "User Interface")
    
    def _create_document_tab(self):
        """Create the Document settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Default document directory
        dir_layout = QHBoxLayout()
        self.default_document_directory = QLineEdit()
        self.default_document_directory.setReadOnly(True)
        dir_layout.addWidget(self.default_document_directory)
        
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_directory)
        dir_layout.addWidget(browse_button)
        
        layout.addRow("Default document directory:", dir_layout)
        
        # Auto-suggest tags
        self.auto_suggest_tags = QCheckBox()
        layout.addRow("Auto-suggest tags:", self.auto_suggest_tags)
        
        # Auto-extract concepts
        self.auto_extract_concepts = QCheckBox()
        layout.addRow("Auto-extract concepts:", self.auto_extract_concepts)
        
        # OCR enabled
        self.ocr_enabled = QCheckBox()
        layout.addRow("Enable OCR for scanned documents:", self.ocr_enabled)
        
        # Highlight color
        color_layout = QHBoxLayout()
        self.highlight_color = QLineEdit()
        self.highlight_color.setReadOnly(True)
        color_layout.addWidget(self.highlight_color)
        
        self.highlight_color_button = QPushButton("Choose...")
        self.highlight_color_button.clicked.connect(self._on_choose_color)
        color_layout.addWidget(self.highlight_color_button)
        
        layout.addRow("Highlight color:", color_layout)
        
        # Add tab
        self.tab_widget.addTab(tab, "Document")
    
    def _create_learning_tab(self):
        """Create the Learning settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Daily new items limit
        self.daily_new_items_limit = QSpinBox()
        self.daily_new_items_limit.setRange(0, 1000)
        layout.addRow("Daily new items limit:", self.daily_new_items_limit)
        
        # Daily review limit
        self.daily_review_limit = QSpinBox()
        self.daily_review_limit.setRange(0, 1000)
        layout.addRow("Daily review limit:", self.daily_review_limit)
        
        # Target retention
        self.target_retention = QDoubleSpinBox()
        self.target_retention.setRange(0.5, 1.0)
        self.target_retention.setSingleStep(0.01)
        self.target_retention.setDecimals(2)
        layout.addRow("Target retention rate:", self.target_retention)
        
        # Allow overdue items
        self.allow_overdue_items = QCheckBox()
        layout.addRow("Allow overdue items:", self.allow_overdue_items)
        
        # Prioritize older items
        self.prioritize_older_items = QCheckBox()
        layout.addRow("Prioritize older items:", self.prioritize_older_items)
        
        # Load balance reviews
        self.load_balance_reviews = QCheckBox()
        layout.addRow("Load balance reviews:", self.load_balance_reviews)
        
        # Add tab
        self.tab_widget.addTab(tab, "Learning")
    
    def _create_algorithm_tab(self):
        """Create the Algorithm settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Minimum interval
        self.minimum_interval = QSpinBox()
        self.minimum_interval.setRange(1, 30)
        self.minimum_interval.setSuffix(" days")
        layout.addRow("Minimum interval:", self.minimum_interval)
        
        # Maximum interval
        self.maximum_interval = QSpinBox()
        self.maximum_interval.setRange(365, 10000)
        self.maximum_interval.setSuffix(" days")
        layout.addRow("Maximum interval:", self.maximum_interval)
        
        # Default easiness
        self.default_easiness = QDoubleSpinBox()
        self.default_easiness.setRange(1.0, 5.0)
        self.default_easiness.setSingleStep(0.1)
        self.default_easiness.setDecimals(1)
        layout.addRow("Default easiness:", self.default_easiness)
        
        # Easiness modifiers
        easiness_group = QGroupBox("Easiness Modifiers")
        easiness_layout = QFormLayout(easiness_group)
        
        self.easiness_grade0 = QDoubleSpinBox()
        self.easiness_grade0.setRange(-1.0, 0.0)
        self.easiness_grade0.setSingleStep(0.05)
        self.easiness_grade0.setDecimals(2)
        easiness_layout.addRow("Grade 0 (Complete blackout):", self.easiness_grade0)
        
        self.easiness_grade1 = QDoubleSpinBox()
        self.easiness_grade1.setRange(-0.5, 0.0)
        self.easiness_grade1.setSingleStep(0.05)
        self.easiness_grade1.setDecimals(2)
        easiness_layout.addRow("Grade 1 (Incorrect, familiar):", self.easiness_grade1)
        
        self.easiness_grade2 = QDoubleSpinBox()
        self.easiness_grade2.setRange(-0.3, 0.0)
        self.easiness_grade2.setSingleStep(0.01)
        self.easiness_grade2.setDecimals(2)
        easiness_layout.addRow("Grade 2 (Incorrect, easy recall):", self.easiness_grade2)
        
        self.easiness_grade3 = QDoubleSpinBox()
        self.easiness_grade3.setRange(-0.1, 0.1)
        self.easiness_grade3.setSingleStep(0.01)
        self.easiness_grade3.setDecimals(2)
        easiness_layout.addRow("Grade 3 (Correct, difficult):", self.easiness_grade3)
        
        self.easiness_grade4 = QDoubleSpinBox()
        self.easiness_grade4.setRange(0.0, 0.2)
        self.easiness_grade4.setSingleStep(0.01)
        self.easiness_grade4.setDecimals(2)
        easiness_layout.addRow("Grade 4 (Correct, hesitation):", self.easiness_grade4)
        
        self.easiness_grade5 = QDoubleSpinBox()
        self.easiness_grade5.setRange(0.0, 0.3)
        self.easiness_grade5.setSingleStep(0.01)
        self.easiness_grade5.setDecimals(2)
        easiness_layout.addRow("Grade 5 (Perfect recall):", self.easiness_grade5)
        
        layout.addRow(easiness_group)
        
        # Interval modifier
        self.interval_modifier = QDoubleSpinBox()
        self.interval_modifier.setRange(0.5, 2.0)
        self.interval_modifier.setSingleStep(0.05)
        self.interval_modifier.setDecimals(2)
        layout.addRow("Interval modifier:", self.interval_modifier)
        
        # Add tab
        self.tab_widget.addTab(tab, "Algorithm")
    
    def _create_backup_tab(self):
        """Create the Backup settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Auto-backup enabled
        self.auto_backup_enabled = QCheckBox()
        layout.addRow("Enable automatic backups:", self.auto_backup_enabled)
        
        # Auto-backup interval
        self.auto_backup_interval = QSpinBox()
        self.auto_backup_interval.setRange(1, 90)
        self.auto_backup_interval.setSuffix(" days")
        layout.addRow("Auto-backup interval:", self.auto_backup_interval)
        
        # Auto-backup count
        self.auto_backup_count = QSpinBox()
        self.auto_backup_count.setRange(1, 50)
        layout.addRow("Number of backups to keep:", self.auto_backup_count)
        
        # Include files in backup
        self.include_files_in_backup = QCheckBox()
        layout.addRow("Include document files in backup:", self.include_files_in_backup)
        
        # Add tab
        self.tab_widget.addTab(tab, "Backup")
    
    def _create_advanced_tab(self):
        """Create the Advanced settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Enable debug logging
        self.enable_debug_logging = QCheckBox()
        layout.addRow("Enable debug logging:", self.enable_debug_logging)
        
        # Max threads
        self.max_threads = QSpinBox()
        self.max_threads.setRange(1, 16)
        layout.addRow("Maximum threads:", self.max_threads)
        
        # SQLite pragma
        sqlite_group = QGroupBox("SQLite Pragma")
        sqlite_layout = QFormLayout(sqlite_group)
        
        self.sqlite_journal_mode = QComboBox()
        self.sqlite_journal_mode.addItems(["DELETE", "TRUNCATE", "PERSIST", "MEMORY", "WAL", "OFF"])
        sqlite_layout.addRow("Journal mode:", self.sqlite_journal_mode)
        
        self.sqlite_synchronous = QComboBox()
        self.sqlite_synchronous.addItems(["OFF", "NORMAL", "FULL", "EXTRA"])
        sqlite_layout.addRow("Synchronous:", self.sqlite_synchronous)
        
        layout.addRow(sqlite_group)
        
        # Add tab
        self.tab_widget.addTab(tab, "Advanced")
    
    def _load_settings(self):
        """Load settings from settings manager."""
        # General settings
        self.auto_save_interval.setValue(
            self.settings_manager.get_setting("general", "auto_save_interval", 5)
        )
        self.max_recent_documents.setValue(
            self.settings_manager.get_setting("general", "max_recent_documents", 10)
        )
        self.startup_show_statistics.setChecked(
            self.settings_manager.get_setting("general", "startup_show_statistics", False)
        )
        
        # UI settings
        theme = self.settings_manager.get_setting("ui", "theme", "light")
        self.theme_combo.setCurrentText(theme.capitalize())
        
        font_family = self.settings_manager.get_setting("ui", "font_family", "Arial")
        if font_family in ["Arial", "Times New Roman", "Courier New", "Verdana", "System"]:
            self.font_family.setCurrentText(font_family)
        else:
            self.font_family.setCurrentText("System")
        
        self.font_size.setValue(
            self.settings_manager.get_setting("ui", "font_size", 12)
        )
        self.show_category_panel.setChecked(
            self.settings_manager.get_setting("ui", "show_category_panel", True)
        )
        self.default_split_ratio.setValue(
            self.settings_manager.get_setting("ui", "default_split_ratio", 0.25)
        )
        
        # Document settings
        self.default_document_directory.setText(
            self.settings_manager.get_setting("document", "default_document_directory", "")
        )
        self.auto_suggest_tags.setChecked(
            self.settings_manager.get_setting("document", "auto_suggest_tags", True)
        )
        self.auto_extract_concepts.setChecked(
            self.settings_manager.get_setting("document", "auto_extract_concepts", False)
        )
        self.ocr_enabled.setChecked(
            self.settings_manager.get_setting("document", "ocr_enabled", True)
        )
        
        highlight_color = self.settings_manager.get_setting("document", "highlight_color", "#FFFF00")
        self.highlight_color.setText(highlight_color)
        self.highlight_color.setStyleSheet(f"background-color: {highlight_color}")
        
        # Learning settings
        self.daily_new_items_limit.setValue(
            self.settings_manager.get_setting("learning", "daily_new_items_limit", 20)
        )
        self.daily_review_limit.setValue(
            self.settings_manager.get_setting("learning", "daily_review_limit", 50)
        )
        self.target_retention.setValue(
            self.settings_manager.get_setting("learning", "target_retention", 0.9)
        )
        self.allow_overdue_items.setChecked(
            self.settings_manager.get_setting("learning", "allow_overdue_items", True)
        )
        self.prioritize_older_items.setChecked(
            self.settings_manager.get_setting("learning", "prioritize_older_items", True)
        )
        self.load_balance_reviews.setChecked(
            self.settings_manager.get_setting("learning", "load_balance_reviews", True)
        )
        
        # Algorithm settings
        self.minimum_interval.setValue(
            self.settings_manager.get_setting("algorithm", "minimum_interval", 1)
        )
        self.maximum_interval.setValue(
            self.settings_manager.get_setting("algorithm", "maximum_interval", 3650)
        )
        self.default_easiness.setValue(
            self.settings_manager.get_setting("algorithm", "default_easiness", 2.5)
        )
        
        easiness_modifier = self.settings_manager.get_setting("algorithm", "easiness_modifier", {})
        self.easiness_grade0.setValue(easiness_modifier.get("grade0", -0.3))
        self.easiness_grade1.setValue(easiness_modifier.get("grade1", -0.15))
        self.easiness_grade2.setValue(easiness_modifier.get("grade2", -0.05))
        self.easiness_grade3.setValue(easiness_modifier.get("grade3", 0.0))
        self.easiness_grade4.setValue(easiness_modifier.get("grade4", 0.05))
        self.easiness_grade5.setValue(easiness_modifier.get("grade5", 0.1))
        
        self.interval_modifier.setValue(
            self.settings_manager.get_setting("algorithm", "interval_modifier", 1.0)
        )
        
        # Backup settings
        self.auto_backup_enabled.setChecked(
            self.settings_manager.get_setting("backup", "auto_backup_enabled", True)
        )
        self.auto_backup_interval.setValue(
            self.settings_manager.get_setting("backup", "auto_backup_interval", 7)
        )
        self.auto_backup_count.setValue(
            self.settings_manager.get_setting("backup", "auto_backup_count", 5)
        )
        self.include_files_in_backup.setChecked(
            self.settings_manager.get_setting("backup", "include_files_in_backup", True)
        )
        
        # Advanced settings
        self.enable_debug_logging.setChecked(
            self.settings_manager.get_setting("advanced", "enable_debug_logging", False)
        )
        self.max_threads.setValue(
            self.settings_manager.get_setting("advanced", "max_threads", 4)
        )
        
        sqlite_pragma = self.settings_manager.get_setting("advanced", "sqlite_pragma", {})
        journal_mode = sqlite_pragma.get("journal_mode", "WAL").upper()
        self.sqlite_journal_mode.setCurrentText(journal_mode)
        
        synchronous = sqlite_pragma.get("synchronous", "NORMAL").upper()
        self.sqlite_synchronous.setCurrentText(synchronous)
    
    def _save_settings(self) -> bool:
        """
        Save settings to settings manager.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # General settings
            self.settings_manager.set_setting("general", "auto_save_interval", self.auto_save_interval.value())
            self.settings_manager.set_setting("general", "max_recent_documents", self.max_recent_documents.value())
            self.settings_manager.set_setting("general", "default_category_id", self.default_category.currentData())
            self.settings_manager.set_setting("general", "startup_show_statistics", self.startup_show_statistics.isChecked())
            
            # UI settings
            self.settings_manager.set_setting("ui", "theme", self.theme_combo.currentText().lower())
            self.settings_manager.set_setting("ui", "font_family", self.font_family.currentText())
            self.settings_manager.set_setting("ui", "font_size", self.font_size.value())
            self.settings_manager.set_setting("ui", "show_category_panel", self.show_category_panel.isChecked())
            self.settings_manager.set_setting("ui", "default_split_ratio", self.default_split_ratio.value())
            
            # Document settings
            self.settings_manager.set_setting("document", "default_document_directory", self.default_document_directory.text())
            self.settings_manager.set_setting("document", "auto_suggest_tags", self.auto_suggest_tags.isChecked())
            self.settings_manager.set_setting("document", "auto_extract_concepts", self.auto_extract_concepts.isChecked())
            self.settings_manager.set_setting("document", "ocr_enabled", self.ocr_enabled.isChecked())
            self.settings_manager.set_setting("document", "highlight_color", self.highlight_color.text())
            
            # Learning settings
            self.settings_manager.set_setting("learning", "daily_new_items_limit", self.daily_new_items_limit.value())
            self.settings_manager.set_setting("learning", "daily_review_limit", self.daily_review_limit.value())
            self.settings_manager.set_setting("learning", "target_retention", self.target_retention.value())
            self.settings_manager.set_setting("learning", "allow_overdue_items", self.allow_overdue_items.isChecked())
            self.settings_manager.set_setting("learning", "prioritize_older_items", self.prioritize_older_items.isChecked())
            self.settings_manager.set_setting("learning", "load_balance_reviews", self.load_balance_reviews.isChecked())
            
            # Algorithm settings
            self.settings_manager.set_setting("algorithm", "minimum_interval", self.minimum_interval.value())
            self.settings_manager.set_setting("algorithm", "maximum_interval", self.maximum_interval.value())
            self.settings_manager.set_setting("algorithm", "default_easiness", self.default_easiness.value())
            
            easiness_modifier = {
                "grade0": self.easiness_grade0.value(),
                "grade1": self.easiness_grade1.value(),
                "grade2": self.easiness_grade2.value(),
                "grade3": self.easiness_grade3.value(),
                "grade4": self.easiness_grade4.value(),
                "grade5": self.easiness_grade5.value()
            }
            self.settings_manager.set_setting("algorithm", "easiness_modifier", easiness_modifier)
            
            self.settings_manager.set_setting("algorithm", "interval_modifier", self.interval_modifier.value())
            
            # Backup settings
            self.settings_manager.set_setting("backup", "auto_backup_enabled", self.auto_backup_enabled.isChecked())
            self.settings_manager.set_setting("backup", "auto_backup_interval", self.auto_backup_interval.value())
            self.settings_manager.set_setting("backup", "auto_backup_count", self.auto_backup_count.value())
            self.settings_manager.set_setting("backup", "include_files_in_backup", self.include_files_in_backup.isChecked())
            
            # Advanced settings
            self.settings_manager.set_setting("advanced", "enable_debug_logging", self.enable_debug_logging.isChecked())
            self.settings_manager.set_setting("advanced", "max_threads", self.max_threads.value())
            
            sqlite_pragma = {
                "journal_mode": self.sqlite_journal_mode.currentText(),
                "synchronous": self.sqlite_synchronous.currentText()
            }
            self.settings_manager.set_setting("advanced", "sqlite_pragma", sqlite_pragma)
            
            # Save to file
            if not self.settings_manager.save_settings():
                logger.error("Failed to save settings")
                return False
            
            return True
            
        except Exception as e:
            logger.exception(f"Error saving settings: {e}")
            return False
    
    @pyqtSlot()
    def _on_browse_directory(self):
        """Handle browse directory button click."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Document Directory",
            self.default_document_directory.text()
        )
        
        if directory:
            self.default_document_directory.setText(directory)
    
    @pyqtSlot()
    def _on_choose_color(self):
        """Handle choose color button click."""
        current_color = QColor(self.highlight_color.text())
        color = QColorDialog.getColor(current_color, self, "Select Highlight Color")
        
        if color.isValid():
            self.highlight_color.setText(color.name())
            self.highlight_color.setStyleSheet(f"background-color: {color.name()}")
    
    @pyqtSlot()
    def _on_import_settings(self):
        """Handle import settings button click."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "", "JSON Files (*.json)"
        )
        
        if filepath:
            # Confirmation dialog
            reply = QMessageBox.warning(
                self, "Import Settings", 
                "Importing settings will replace all current settings. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                if self.settings_manager.import_settings(filepath):
                    # Reload settings
                    self._load_settings()
                    
                    QMessageBox.information(
                        self, "Import Successful", 
                        "Settings imported successfully"
                    )
                else:
                    QMessageBox.warning(
                        self, "Import Failed", 
                        "Failed to import settings"
                    )
    
    @pyqtSlot()
    def _on_export_settings(self):
        """Handle export settings button click."""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Settings", "", "JSON Files (*.json)"
        )
        
        if filepath:
            if not filepath.endswith(".json"):
                filepath += ".json"
                
            if self.settings_manager.export_settings(filepath):
                QMessageBox.information(
                    self, "Export Successful", 
                    "Settings exported successfully"
                )
            else:
                QMessageBox.warning(
                    self, "Export Failed", 
                    "Failed to export settings"
                )
    
    @pyqtSlot()
    def _on_accept(self):
        """Handle OK button click."""
        if self._save_settings():
            self.settingsChanged.emit()
            self.accept()
        else:
            QMessageBox.warning(
                self, "Error", 
                "Failed to save settings"
            )
    
    @pyqtSlot()
    def _on_apply(self):
        """Handle Apply button click."""
        if self._save_settings():
            self.settingsChanged.emit()
        else:
            QMessageBox.warning(
                self, "Error", 
                "Failed to save settings"
            )
    
    @pyqtSlot()
    def _on_reset(self):
        """Handle Reset button click."""
        # Confirmation dialog
        reply = QMessageBox.warning(
            self, "Reset Settings", 
            "This will reset all settings to default values. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Reset settings
            self.settings_manager.reset_settings()
            
            # Reload settings
            self._load_settings()
