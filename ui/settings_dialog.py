# ui/settings_dialog.py

import os
import logging
from typing import Dict, Any, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTabWidget, QWidget, QFormLayout,
    QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
    QComboBox, QColorDialog, QFileDialog, QGroupBox,
    QMessageBox, QDialogButtonBox, QInputDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSettings
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QApplication

from core.utils.settings_manager import SettingsManager
from core.utils.theme_manager import ThemeManager

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
        self._create_rss_tab()
        self._create_api_tab()
        self._create_backup_tab()
        self._create_advanced_tab()
        
        main_layout.addWidget(self.tab_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Reset button
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._on_reset)
        button_layout.addWidget(self.reset_button)
        
        # Import/Export buttons
        self.import_button = QPushButton("Import Settings")
        self.import_button.clicked.connect(self._on_import_settings)
        button_layout.addWidget(self.import_button)
        
        self.export_button = QPushButton("Export Settings")
        self.export_button.clicked.connect(self._on_export_settings)
        button_layout.addWidget(self.export_button)
        
        button_layout.addStretch()
        
        # Standard buttons
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply)
        button_layout.addWidget(self.apply_button)
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self._on_accept)
        button_layout.addWidget(self.ok_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
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
        theme_layout = QFormLayout(theme_group)
        
        # Get theme options from theme manager
        if not hasattr(self, 'theme_manager'):
            self.theme_manager = ThemeManager(self.settings_manager)
        
        # Theme selector
        self.theme_combo = QComboBox()
        
        # Add built-in themes and get available custom themes
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("System", "system")
        
        # Load available custom themes
        custom_themes = self.theme_manager.get_available_themes()
        if custom_themes:
            self.theme_combo.insertSeparator(self.theme_combo.count())
            for theme_name in custom_themes:
                if theme_name not in ["light", "dark", "system"]:
                    self.theme_combo.addItem(f"Custom: {theme_name}", theme_name)
        
        # Set current theme
        current_theme = self.settings_manager.get_setting("ui", "theme", "light")
        index = self.theme_combo.findData(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        
        theme_layout.addRow("Theme:", self.theme_combo)
        
        # Custom theme file
        custom_theme_layout = QHBoxLayout()
        self.theme_file_path = QLineEdit()
        theme_file = self.settings_manager.get_setting("ui", "theme_file", "")
        self.theme_file_path.setText(theme_file)
        custom_theme_layout.addWidget(self.theme_file_path)
        
        self.theme_browse_button = QPushButton("Browse...")
        self.theme_browse_button.clicked.connect(self._on_browse_theme)
        custom_theme_layout.addWidget(self.theme_browse_button)
        
        theme_layout.addRow("Custom theme file:", custom_theme_layout)
        
        # Connect theme combo change to update UI
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        
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
        
        # Font family
        self.font_family = QComboBox()
        self.font_family.addItems(["Arial", "Times New Roman", "Courier New", "Verdana", "System"])
        current_font = self.settings_manager.get_setting("ui", "font_family", "System")
        index = self.font_family.findText(current_font)
        if index >= 0:
            self.font_family.setCurrentIndex(index)
        layout_layout.addRow("Font family:", self.font_family)
        
        # Font size
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        self.font_size.setValue(self.settings_manager.get_setting("ui", "font_size", 10))
        layout_layout.addRow("Font size:", self.font_size)
        
        # Show category panel
        self.show_category_panel = QCheckBox()
        self.show_category_panel.setChecked(self.settings_manager.get_setting("ui", "show_category_panel", True))
        layout_layout.addRow("Show category panel:", self.show_category_panel)
        
        # Default split ratio
        self.default_split_ratio = QDoubleSpinBox()
        self.default_split_ratio.setRange(0.1, 0.5)
        self.default_split_ratio.setSingleStep(0.05)
        self.default_split_ratio.setValue(self.settings_manager.get_setting("ui", "default_split_ratio", 0.3))
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
    
    def _create_rss_tab(self):
        """Create RSS settings tab."""
        rss_tab = QWidget()
        layout = QVBoxLayout(rss_tab)
        
        # Add RSS settings
        settings_group = QGroupBox("RSS Feed Settings")
        settings_layout = QFormLayout(settings_group)
        
        # Default check frequency
        self.default_check_frequency = QSpinBox()
        self.default_check_frequency.setRange(5, 1440)  # 5 minutes to 24 hours
        self.default_check_frequency.setValue(60)
        self.default_check_frequency.setSuffix(" minutes")
        settings_layout.addRow("Default check frequency:", self.default_check_frequency)
        
        # Check interval
        self.check_interval = QSpinBox()
        self.check_interval.setRange(1, 60)  # 1 to 60 minutes
        self.check_interval.setValue(15)
        self.check_interval.setSuffix(" minutes")
        settings_layout.addRow("Application check interval:", self.check_interval)
        
        # Default priority
        self.default_priority = QSpinBox()
        self.default_priority.setRange(1, 100)
        self.default_priority.setValue(50)
        settings_layout.addRow("Default item priority:", self.default_priority)
        
        # Default auto-import
        self.default_auto_import = QCheckBox()
        self.default_auto_import.setChecked(True)
        settings_layout.addRow("Auto-import new items by default:", self.default_auto_import)
        
        # Default max items to keep
        self.default_max_items = QSpinBox()
        self.default_max_items.setRange(0, 1000)
        self.default_max_items.setValue(50)
        self.default_max_items.setSpecialValueText("Keep all")  # For value 0
        settings_layout.addRow("Default max items to keep:", self.default_max_items)
        
        layout.addWidget(settings_group)
        
        # Manage button
        manage_layout = QHBoxLayout()
        manage_layout.addStretch()
        
        self.manage_feeds_button = QPushButton("Manage RSS Feeds")
        self.manage_feeds_button.clicked.connect(self._on_manage_feeds)
        manage_layout.addWidget(self.manage_feeds_button)
        
        layout.addLayout(manage_layout)
        
        # Add stretch to push settings to the top
        layout.addStretch()
        
        self.tab_widget.addTab(rss_tab, "RSS Feeds")
    
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
        """Load settings into UI elements."""
        # Get current settings
        
        # General tab
        self.theme_combo.setCurrentIndex(
            self.theme_combo.findText(
                self.settings_manager.get_setting("ui", "theme", "Light")
            )
        )
        
        self.startup_show_statistics.setChecked(
            self.settings_manager.get_setting("general", "startup_show_statistics", False)
        )
        
        self.auto_save_interval.setValue(
            self.settings_manager.get_setting("general", "auto_save_interval", 5)
        )
        
        self.max_recent_documents.setValue(
            self.settings_manager.get_setting("general", "max_recent_documents", 10)
        )
        
        self.show_category_panel.setChecked(
            self.settings_manager.get_setting("ui", "show_category_panel", True)
        )
        
        self.font_size.setValue(
            self.settings_manager.get_setting("ui", "font_size", 12)
        )
        
        # Document tab
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
        
        # Learning tab
        self.daily_new_items_limit.setValue(
            self.settings_manager.get_setting("learning", "daily_new_items_limit", 20)
        )
        
        self.daily_review_limit.setValue(
            self.settings_manager.get_setting("learning", "daily_review_limit", 50)
        )
        
        self.target_retention.setValue(
            self.settings_manager.get_setting("learning", "target_retention", 0.9)
        )
        
        # Algorithm tab
        self.minimum_interval.setValue(
            self.settings_manager.get_setting("algorithm", "minimum_interval", 1)
        )
        
        self.maximum_interval.setValue(
            self.settings_manager.get_setting("algorithm", "maximum_interval", 365)
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
        
        # RSS tab
        self.default_check_frequency.setValue(
            self.settings_manager.get_setting("rss", "default_check_frequency", 60)
        )
        
        self.check_interval.setValue(
            self.settings_manager.get_setting("rss", "check_interval_minutes", 15)
        )
        
        self.default_priority.setValue(
            self.settings_manager.get_setting("rss", "default_priority", 50)
        )
        
        self.default_auto_import.setChecked(
            self.settings_manager.get_setting("rss", "default_auto_import", True)
        )
        
        self.default_max_items.setValue(
            self.settings_manager.get_setting("rss", "default_max_items", 50)
        )
        
        # API tab
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
        """Save settings from UI elements to settings manager."""
        try:
            # UI Theme settings
            theme_data = self.theme_combo.currentData()
            self.settings_manager.set_setting("ui", "theme", theme_data)
            
            # Check if it's a custom theme
            is_custom = theme_data not in ["light", "dark", "system"]
            self.settings_manager.set_setting("ui", "custom_theme", is_custom)
            
            # Save custom theme path if applicable
            if is_custom:
                self.settings_manager.set_setting("ui", "theme_file", self.theme_file_path.text())
            
            # General tab settings
            self.settings_manager.set_setting(
                "general", "startup_show_statistics", self.startup_show_statistics.isChecked()
            )
            
            self.settings_manager.set_setting(
                "general", "auto_save_interval", self.auto_save_interval.value()
            )
            
            self.settings_manager.set_setting(
                "general", "max_recent_documents", self.max_recent_documents.value()
            )
            
            self.settings_manager.set_setting(
                "ui", "show_category_panel", self.show_category_panel.isChecked()
            )
            
            self.settings_manager.set_setting(
                "ui", "font_size", self.font_size.value()
            )
            
            # Document tab
            self.settings_manager.set_setting(
                "document", "default_document_directory", self.default_document_directory.text()
            )
            
            self.settings_manager.set_setting(
                "document", "auto_suggest_tags", self.auto_suggest_tags.isChecked()
            )
            
            self.settings_manager.set_setting(
                "document", "auto_extract_concepts", self.auto_extract_concepts.isChecked()
            )
            
            self.settings_manager.set_setting(
                "document", "ocr_enabled", self.ocr_enabled.isChecked()
            )
            
            self.settings_manager.set_setting(
                "document", "highlight_color", self.highlight_color.text()
            )
            
            # Learning tab
            self.settings_manager.set_setting(
                "learning", "daily_new_items_limit", self.daily_new_items_limit.value()
            )
            
            self.settings_manager.set_setting(
                "learning", "daily_review_limit", self.daily_review_limit.value()
            )
            
            self.settings_manager.set_setting(
                "learning", "target_retention", self.target_retention.value()
            )
            
            # Algorithm tab
            self.settings_manager.set_setting(
                "algorithm", "minimum_interval", self.minimum_interval.value()
            )
            
            self.settings_manager.set_setting(
                "algorithm", "maximum_interval", self.maximum_interval.value()
            )
            
            self.settings_manager.set_setting(
                "algorithm", "default_easiness", self.default_easiness.value()
            )
            
            easiness_modifier = {
                "grade0": self.easiness_grade0.value(),
                "grade1": self.easiness_grade1.value(),
                "grade2": self.easiness_grade2.value(),
                "grade3": self.easiness_grade3.value(),
                "grade4": self.easiness_grade4.value(),
                "grade5": self.easiness_grade5.value()
            }
            self.settings_manager.set_setting("algorithm", "easiness_modifier", easiness_modifier)
            
            self.settings_manager.set_setting(
                "algorithm", "interval_modifier", self.interval_modifier.value()
            )
            
            # RSS tab
            self.settings_manager.set_setting(
                "rss", "default_check_frequency", self.default_check_frequency.value()
            )
            
            self.settings_manager.set_setting(
                "rss", "check_interval_minutes", self.check_interval.value()
            )
            
            self.settings_manager.set_setting(
                "rss", "default_priority", self.default_priority.value()
            )
            
            self.settings_manager.set_setting(
                "rss", "default_auto_import", self.default_auto_import.isChecked()
            )
            
            self.settings_manager.set_setting(
                "rss", "default_max_items", self.default_max_items.value()
            )
            
            # API tab
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
    
    def _update_theme_combo(self, theme_name):
        """Update the theme combo box to select the newly created theme."""
        # Check if the theme is already in the combo box
        index = self.theme_combo.findData(theme_name)
        if index >= 0:
            # Select it if it exists
            self.theme_combo.setCurrentIndex(index)
        else:
            # Add it if it doesn't exist
            self.theme_combo.addItem(f"Custom: {theme_name}", theme_name)
            self.theme_combo.setCurrentIndex(self.theme_combo.count() - 1)

    def _on_browse_theme(self):
        """Browse for a custom theme file."""
        try:
            # Create theme manager if needed
            if not hasattr(self, 'theme_manager'):
                self.theme_manager = ThemeManager(self.settings_manager)
            
            # Ask what type of theme file to create/browse
            theme_type, ok = QInputDialog.getItem(
                self, "Theme File Type", 
                "Select theme file type:",
                ["JSON Color Theme", "QSS Style Sheet", "Create New Theme Template"], 
                0, False
            )
            
            if not ok:
                return
                
            if "Create New" in theme_type:
                # Create a new theme template
                file_path, _ = QFileDialog.getSaveFileName(
                    self, "Save Theme Template", "", "JSON Files (*.json)"
                )
                
                if file_path:
                    if not file_path.lower().endswith('.json'):
                        file_path += '.json'
                        
                    # Create template
                    if self.theme_manager.create_theme_template(file_path):
                        # Get theme name from file path
                        theme_name = os.path.basename(file_path)
                        if theme_name.lower().endswith('.json'):
                            theme_name = theme_name[:-5]  # Remove .json extension
                            
                        self.theme_file_path.setText(file_path)
                        
                        # Apply the new theme immediately
                        app = QApplication.instance()
                        if app:
                            # Save settings for custom theme
                            self.settings_manager.set_setting("ui", "custom_theme", True)
                            self.settings_manager.set_setting("ui", "theme_file", file_path)
                            self.settings_manager.set_setting("ui", "theme", theme_name)
                            
                            # Apply the theme
                            self.theme_manager.apply_theme(app, theme_name=theme_name, 
                                                        custom_theme_path=file_path)
                            
                            # Save settings
                            self.settings_manager.save_settings()
                            
                            # Update theme combo box to select the new theme
                            self._update_theme_combo(theme_name)
                            
                            # Emit signal to notify application
                            self.settingsChanged.emit()
                        
                        QMessageBox.information(
                            self, "Theme Created and Applied", 
                            f"A new theme has been created and applied from {file_path}.\n\n"
                            "You can edit this file with a text editor to further customize your theme."
                        )
                
            else:
                # Set file filter based on selection
                file_filter = "JSON Files (*.json)" if "JSON" in theme_type else "Style Sheets (*.qss)"
                
                # Browse for existing theme file
                file_path, _ = QFileDialog.getOpenFileName(
                    self, "Select Theme File", "", file_filter
                )
                
                if file_path:
                    # Get theme name from file path
                    theme_name = os.path.basename(file_path)
                    if theme_name.lower().endswith('.json'):
                        theme_name = theme_name[:-5]  # Remove .json extension
                    elif theme_name.lower().endswith('.qss'):
                        theme_name = theme_name[:-4]  # Remove .qss extension
                        
                    self.theme_file_path.setText(file_path)
                    
                    # Apply the theme immediately
                    app = QApplication.instance()
                    if app:
                        # Save settings for custom theme
                        self.settings_manager.set_setting("ui", "custom_theme", True)
                        self.settings_manager.set_setting("ui", "theme_file", file_path)
                        self.settings_manager.set_setting("ui", "theme", theme_name)
                        
                        # Apply the theme
                        success = self.theme_manager.apply_theme(app, theme_name=theme_name, 
                                                                custom_theme_path=file_path)
                        
                        # Save settings
                        self.settings_manager.save_settings()
                        
                        # Update theme combo box to select the new theme
                        self._update_theme_combo(theme_name)
                        
                        # Emit signal to notify application
                        self.settingsChanged.emit()
                        
                        if success:
                            QMessageBox.information(
                                self, "Theme Applied", 
                                f"The theme has been applied from {file_path}."
                            )
                        
        except Exception as e:
            logger.exception(f"Error browsing for theme: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error browsing for or applying theme: {str(e)}"
            )
            
    def _on_theme_changed(self, index):
        """Handle theme selection changes."""
        try:
            # Get the selected theme data
            selected_theme = self.theme_combo.itemData(index)
            
            # Update file path field visibility based on theme selection
            is_custom = selected_theme not in ["light", "dark", "system"]
            
            # If it's a custom theme, show details of the theme file
            if is_custom:
                # Get path to custom theme
                theme_path = self.theme_manager.get_theme_path(selected_theme)
                if theme_path and os.path.exists(theme_path):
                    self.theme_file_path.setText(theme_path)
            
            # Apply the theme immediately
            app = QApplication.instance()
            if app:
                if is_custom:
                    # For custom themes
                    custom_path = self.theme_file_path.text()
                    if custom_path and os.path.exists(custom_path):
                        # Save settings for custom theme
                        self.settings_manager.set_setting("ui", "custom_theme", True)
                        self.settings_manager.set_setting("ui", "theme_file", custom_path)
                        self.settings_manager.set_setting("ui", "theme", selected_theme)
                        
                        # Apply the theme
                        self.theme_manager.apply_theme(app, theme_name=selected_theme, 
                                                    custom_theme_path=custom_path)
                    else:
                        logger.warning(f"Custom theme path not valid: {custom_path}")
                else:
                    # For built-in themes
                    self.settings_manager.set_setting("ui", "theme", selected_theme)
                    self.settings_manager.set_setting("ui", "custom_theme", False)
                    self.settings_manager.set_setting("ui", "theme_file", "")  # Clear custom theme path
                    self.theme_manager.apply_theme(app, theme_name=selected_theme)
                
                # Save the settings
                self.settings_manager.save_settings()
                
                # Inform the application that settings changed
                self.settingsChanged.emit()
                
                logger.info(f"Theme applied: {selected_theme}")
                
        except Exception as e:
            logger.exception(f"Error changing theme: {e}")
            QMessageBox.warning(
                self, "Theme Error", 
                f"Failed to apply theme: {str(e)}"
            )

    def _on_manage_feeds(self):
        """Open the RSS feed management dialog."""
        from ui.dialogs.rss_feed_dialog import RSSFeedDialog
        from core.utils.rss_feed_manager import RSSFeedManager
        
        # Make sure we save any settings changes first
        self._save_settings()
        
        # Create RSS feed manager
        from core.knowledge_base.models import init_database
        db_session = init_database()
        rss_manager = RSSFeedManager(db_session, self.settings_manager)
        
        # Create and show dialog
        dialog = RSSFeedDialog(db_session, rss_manager, self)
        dialog.exec()
        
        # Refresh settings in case any were changed
        self._load_settings()
