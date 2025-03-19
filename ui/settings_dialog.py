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
        self._create_api_tab()
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
        ui_tab = QWidget()
        layout = QVBoxLayout(ui_tab)
        
        # UI theme group
        theme_group = QGroupBox("UI Theme")
        theme_layout = QVBoxLayout(theme_group)
        
        self.dark_mode_checkbox = QCheckBox("Use dark mode")
        dark_mode = self.settings_manager.get_setting("ui", "dark_mode", False)
        self.dark_mode_checkbox.setChecked(dark_mode)
        theme_layout.addWidget(self.dark_mode_checkbox)
        
        self.custom_theme_checkbox = QCheckBox("Use custom theme")
        custom_theme = self.settings_manager.get_setting("ui", "custom_theme", False)
        self.custom_theme_checkbox.setChecked(custom_theme)
        theme_layout.addWidget(self.custom_theme_checkbox)
        
        self.theme_file_path = QLineEdit()
        theme_file = self.settings_manager.get_setting("ui", "theme_file", "")
        self.theme_file_path.setText(theme_file)
        self.theme_file_path.setEnabled(custom_theme)
        theme_layout.addWidget(self.theme_file_path)
        
        self.theme_browse_button = QPushButton("Browse...")
        self.theme_browse_button.clicked.connect(self._on_browse_theme)
        self.theme_browse_button.setEnabled(custom_theme)
        theme_layout.addWidget(self.theme_browse_button)
        
        self.custom_theme_checkbox.toggled.connect(self.theme_file_path.setEnabled)
        self.custom_theme_checkbox.toggled.connect(self.theme_browse_button.setEnabled)
        
        layout.addWidget(theme_group)
        
        # Web features group
        web_group = QGroupBox("Web Features")
        web_layout = QVBoxLayout(web_group)
        
        self.web_browser_checkbox = QCheckBox("Enable web browser for extracts")
        web_browser_enabled = self.settings_manager.get_setting("ui", "web_browser_enabled", True)
        self.web_browser_checkbox.setChecked(web_browser_enabled)
        self.web_browser_checkbox.setToolTip("Enables browsing the web and creating extracts from websites")
        web_layout.addWidget(self.web_browser_checkbox)
        
        self.auto_save_web_checkbox = QCheckBox("Auto-save extracted websites")
        auto_save_web = self.settings_manager.get_setting("ui", "auto_save_web", True)
        self.auto_save_web_checkbox.setChecked(auto_save_web)
        self.auto_save_web_checkbox.setToolTip("Automatically save web pages when creating extracts from them")
        web_layout.addWidget(self.auto_save_web_checkbox)
        
        layout.addWidget(web_group)
        
        # Layout settings group
        layout_group = QGroupBox("Layout Settings")
        layout_layout = QFormLayout(layout_group)
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        layout_layout.addRow("Theme:", self.theme_combo)
        
        # Font family
        self.font_family = QComboBox()
        self.font_family.addItems(["Arial", "Times New Roman", "Courier New", "Verdana", "System"])
        layout_layout.addRow("Font family:", self.font_family)
        
        # Font size
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        layout_layout.addRow("Font size:", self.font_size)
        
        # Show category panel
        self.show_category_panel = QCheckBox()
        layout_layout.addRow("Show category panel:", self.show_category_panel)
        
        # Default split ratio
        self.default_split_ratio = QDoubleSpinBox()
        self.default_split_ratio.setRange(0.1, 0.5)
        self.default_split_ratio.setSingleStep(0.05)
        layout_layout.addRow("Default split ratio:", self.default_split_ratio)
        
        layout.addWidget(layout_group)
        
        # Add tab
        self.tab_widget.addTab(ui_tab, "User Interface")
    
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
    
    def _create_api_tab(self):
        """Create the API settings tab."""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        
        # Create tabs for different API services
        api_tabs = QTabWidget()
        
        # Jina.ai tab
        jina_tab = QWidget()
        jina_layout = QFormLayout(jina_tab)
        
        # Jina.ai API key
        jina_key_layout = QHBoxLayout()
        self.jina_api_key = QLineEdit()
        self.jina_api_key.setEchoMode(QLineEdit.EchoMode.Password)  # Hide API key
        jina_key_layout.addWidget(self.jina_api_key)
        
        # Button to show/hide password
        self.show_jina_key_button = QPushButton("Show")
        self.show_jina_key_button.setCheckable(True)
        self.show_jina_key_button.toggled.connect(lambda checked: self._toggle_password_visibility(self.jina_api_key, self.show_jina_key_button, checked))
        jina_key_layout.addWidget(self.show_jina_key_button)
        
        jina_layout.addRow("API Key:", jina_key_layout)
        
        # Add a descriptive label
        jina_info_label = QLabel(
            "Jina.ai is used to fetch website content for importing into the application.\n"
            "A default API key is provided, but you can enter your own key for higher rate limits."
        )
        jina_info_label.setWordWrap(True)
        jina_layout.addRow("", jina_info_label)
        
        api_tabs.addTab(jina_tab, "Jina.ai")
        
        # OpenAI tab
        openai_tab = QWidget()
        openai_layout = QFormLayout(openai_tab)
        
        # OpenAI API key
        openai_key_layout = QHBoxLayout()
        self.openai_api_key = QLineEdit()
        self.openai_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        openai_key_layout.addWidget(self.openai_api_key)
        
        self.show_openai_key_button = QPushButton("Show")
        self.show_openai_key_button.setCheckable(True)
        self.show_openai_key_button.toggled.connect(lambda checked: self._toggle_password_visibility(self.openai_api_key, self.show_openai_key_button, checked))
        openai_key_layout.addWidget(self.show_openai_key_button)
        
        openai_layout.addRow("API Key:", openai_key_layout)
        
        # OpenAI model selection
        self.openai_model = QComboBox()
        self.openai_model.addItems(["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"])
        openai_layout.addRow("Model:", self.openai_model)
        
        api_tabs.addTab(openai_tab, "OpenAI")
        
        # Gemini tab
        gemini_tab = QWidget()
        gemini_layout = QFormLayout(gemini_tab)
        
        # Gemini API key
        gemini_key_layout = QHBoxLayout()
        self.gemini_api_key = QLineEdit()
        self.gemini_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        gemini_key_layout.addWidget(self.gemini_api_key)
        
        self.show_gemini_key_button = QPushButton("Show")
        self.show_gemini_key_button.setCheckable(True)
        self.show_gemini_key_button.toggled.connect(lambda checked: self._toggle_password_visibility(self.gemini_api_key, self.show_gemini_key_button, checked))
        gemini_key_layout.addWidget(self.show_gemini_key_button)
        
        gemini_layout.addRow("API Key:", gemini_key_layout)
        
        # Gemini model selection
        self.gemini_model = QComboBox()
        self.gemini_model.addItems(["gemini-pro", "gemini-1.5-pro"])
        gemini_layout.addRow("Model:", self.gemini_model)
        
        api_tabs.addTab(gemini_tab, "Gemini")
        
        # Claude tab
        claude_tab = QWidget()
        claude_layout = QFormLayout(claude_tab)
        
        # Claude API key
        claude_key_layout = QHBoxLayout()
        self.claude_api_key = QLineEdit()
        self.claude_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        claude_key_layout.addWidget(self.claude_api_key)
        
        self.show_claude_key_button = QPushButton("Show")
        self.show_claude_key_button.setCheckable(True)
        self.show_claude_key_button.toggled.connect(lambda checked: self._toggle_password_visibility(self.claude_api_key, self.show_claude_key_button, checked))
        claude_key_layout.addWidget(self.show_claude_key_button)
        
        claude_layout.addRow("API Key:", claude_key_layout)
        
        # Claude model selection
        self.claude_model = QComboBox()
        self.claude_model.addItems(["claude-3-haiku-20240307", "claude-3-sonnet-20240229", "claude-3-opus-20240229"])
        claude_layout.addRow("Model:", self.claude_model)
        
        api_tabs.addTab(claude_tab, "Claude")
        
        # OpenRouter tab
        openrouter_tab = QWidget()
        openrouter_layout = QFormLayout(openrouter_tab)
        
        # OpenRouter API key
        openrouter_key_layout = QHBoxLayout()
        self.openrouter_api_key = QLineEdit()
        self.openrouter_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        openrouter_key_layout.addWidget(self.openrouter_api_key)
        
        self.show_openrouter_key_button = QPushButton("Show")
        self.show_openrouter_key_button.setCheckable(True)
        self.show_openrouter_key_button.toggled.connect(lambda checked: self._toggle_password_visibility(self.openrouter_api_key, self.show_openrouter_key_button, checked))
        openrouter_key_layout.addWidget(self.show_openrouter_key_button)
        
        openrouter_layout.addRow("API Key:", openrouter_key_layout)
        
        # OpenRouter model selection
        self.openrouter_model = QLineEdit("openai/gpt-3.5-turbo")
        openrouter_layout.addRow("Model:", self.openrouter_model)
        
        # Add description
        openrouter_info = QLabel(
            "OpenRouter provides access to many LLMs through a single API.\n"
            "Model format is provider/model-name (e.g., anthropic/claude-3-opus)"
        )
        openrouter_info.setWordWrap(True)
        openrouter_layout.addRow("", openrouter_info)
        
        api_tabs.addTab(openrouter_tab, "OpenRouter")
        
        # Ollama tab
        ollama_tab = QWidget()
        ollama_layout = QFormLayout(ollama_tab)
        
        # Ollama host
        self.ollama_host = QLineEdit("http://localhost:11434")
        ollama_layout.addRow("Host:", self.ollama_host)
        
        # Ollama model selection
        self.ollama_model = QLineEdit("llama3")
        ollama_layout.addRow("Model:", self.ollama_model)
        
        # Test connection button
        test_ollama_button = QPushButton("Test Connection")
        test_ollama_button.clicked.connect(self._test_ollama_connection)
        ollama_layout.addRow("", test_ollama_button)
        
        api_tabs.addTab(ollama_tab, "Ollama")
        
        # Default LLM service selection
        default_service_layout = QFormLayout()
        self.default_llm_service = QComboBox()
        self.default_llm_service.addItems(["OpenAI", "Gemini", "Claude", "OpenRouter", "Ollama"])
        default_service_layout.addRow("Default LLM service:", self.default_llm_service)
        
        # Add tabs to main layout
        tab_layout.addLayout(default_service_layout)
        tab_layout.addWidget(api_tabs)
        
        # Add tab
        self.tab_widget.addTab(tab, "API Settings")
    
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
        
        layout.addWidget(sqlite_group)
        
        # Add tab
        self.tab_widget.addTab(tab, "Advanced")
    
    def _toggle_password_visibility(self, line_edit, button, show):
        """Toggle password visibility for API keys."""
        if show:
            line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            button.setText("Hide")
        else:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            button.setText("Show")
    
    def _test_ollama_connection(self):
        """Test the Ollama connection."""
        import requests
        
        host = self.ollama_host.text().strip()
        try:
            response = requests.get(f"{host}/api/version", timeout=5)
            if response.status_code == 200:
                QMessageBox.information(
                    self, "Connection Successful", 
                    f"Successfully connected to Ollama at {host}\n"
                    f"Version: {response.json().get('version', 'unknown')}"
                )
            else:
                QMessageBox.warning(
                    self, "Connection Failed", 
                    f"Failed to connect to Ollama at {host}\n"
                    f"Status code: {response.status_code}"
                )
        except Exception as e:
            QMessageBox.warning(
                self, "Connection Failed", 
                f"Failed to connect to Ollama at {host}\n"
                f"Error: {str(e)}"
            )
    
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
        
        # Web browser settings
        self.web_browser_checkbox.setChecked(
            self.settings_manager.get_setting("ui", "web_browser_enabled", True)
        )
        self.auto_save_web_checkbox.setChecked(
            self.settings_manager.get_setting("ui", "auto_save_web", True)
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
        
        # API settings
        self.jina_api_key.setText(
            self.settings_manager.get_setting("api", "jina_api_key", "")
        )
        self.openai_api_key.setText(
            self.settings_manager.get_setting("api", "openai_api_key", "")
        )
        openai_model = self.settings_manager.get_setting("api", "openai_model", "gpt-3.5-turbo")
        index = self.openai_model.findText(openai_model)
        if index >= 0:
            self.openai_model.setCurrentIndex(index)
            
        self.gemini_api_key.setText(
            self.settings_manager.get_setting("api", "gemini_api_key", "")
        )
        gemini_model = self.settings_manager.get_setting("api", "gemini_model", "gemini-pro")
        index = self.gemini_model.findText(gemini_model)
        if index >= 0:
            self.gemini_model.setCurrentIndex(index)
            
        self.claude_api_key.setText(
            self.settings_manager.get_setting("api", "claude_api_key", "")
        )
        claude_model = self.settings_manager.get_setting("api", "claude_model", "claude-3-haiku-20240307")
        index = self.claude_model.findText(claude_model)
        if index >= 0:
            self.claude_model.setCurrentIndex(index)
            
        self.openrouter_api_key.setText(
            self.settings_manager.get_setting("api", "openrouter_api_key", "")
        )
        self.openrouter_model.setText(
            self.settings_manager.get_setting("api", "openrouter_model", "openai/gpt-3.5-turbo")
        )
        
        self.ollama_host.setText(
            self.settings_manager.get_setting("api", "ollama_host", "http://localhost:11434")
        )
        self.ollama_model.setText(
            self.settings_manager.get_setting("api", "ollama_model", "llama3")
        )
        
        default_llm = self.settings_manager.get_setting("api", "default_llm_service", "OpenAI")
        index = self.default_llm_service.findText(default_llm)
        if index >= 0:
            self.default_llm_service.setCurrentIndex(index)
    
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
            
            # Web browser settings
            self.settings_manager.set_setting("ui", "web_browser_enabled", self.web_browser_checkbox.isChecked())
            self.settings_manager.set_setting("ui", "auto_save_web", self.auto_save_web_checkbox.isChecked())
            
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
            
            # API settings
            self.settings_manager.set_setting("api", "jina_api_key", self.jina_api_key.text())
            self.settings_manager.set_setting("api", "openai_api_key", self.openai_api_key.text())
            self.settings_manager.set_setting("api", "openai_model", self.openai_model.currentText())
            self.settings_manager.set_setting("api", "gemini_api_key", self.gemini_api_key.text())
            self.settings_manager.set_setting("api", "gemini_model", self.gemini_model.currentText())
            self.settings_manager.set_setting("api", "claude_api_key", self.claude_api_key.text())
            self.settings_manager.set_setting("api", "claude_model", self.claude_model.currentText())
            self.settings_manager.set_setting("api", "openrouter_api_key", self.openrouter_api_key.text())
            self.settings_manager.set_setting("api", "openrouter_model", self.openrouter_model.text())
            self.settings_manager.set_setting("api", "ollama_host", self.ollama_host.text())
            self.settings_manager.set_setting("api", "ollama_model", self.ollama_model.text())
            self.settings_manager.set_setting("api", "default_llm_service", self.default_llm_service.currentText())
            
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
