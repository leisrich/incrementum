from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QDialogButtonBox,
    QCheckBox, QGroupBox, QRadioButton
)
from PyQt6.QtCore import Qt, pyqtSlot

class URLImportDialog(QDialog):
    """Dialog for importing content from a URL."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.setWindowTitle("Import from URL")
        self.setMinimumWidth(500)
        
        self._create_ui()
    
    def _create_ui(self):
        """Create the UI layout."""
        layout = QVBoxLayout(self)
        
        # URL input
        url_layout = QHBoxLayout()
        url_label = QLabel("URL:")
        self.url_line = QLineEdit()
        self.url_line.setPlaceholderText("https://example.com")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_line)
        layout.addLayout(url_layout)
        
        # Import options
        options_group = QGroupBox("Import Options")
        options_layout = QVBoxLayout(options_group)
        
        # Jina.ai option
        self.use_jina_checkbox = QCheckBox("Use Jina.ai for better web content extraction")
        self.use_jina_checkbox.setChecked(True)
        self.use_jina_checkbox.setToolTip(
            "Jina.ai provides enhanced web content extraction with better formatting and images."
        )
        options_layout.addWidget(self.use_jina_checkbox)
        
        # Add additional options
        self.include_images_checkbox = QCheckBox("Include images")
        self.include_images_checkbox.setChecked(True)
        options_layout.addWidget(self.include_images_checkbox)
        
        self.extract_main_content_checkbox = QCheckBox("Extract main content only (filter navigation, ads, etc.)")
        self.extract_main_content_checkbox.setChecked(True)
        options_layout.addWidget(self.extract_main_content_checkbox)
        
        # LLM processing options
        self.process_with_llm_checkbox = QCheckBox("Process content with LLM")
        self.process_with_llm_checkbox.setChecked(False)
        self.process_with_llm_checkbox.setToolTip(
            "Use an LLM (like OpenAI, Claude, etc.) to generate a summary or article from the content."
        )
        options_layout.addWidget(self.process_with_llm_checkbox)
        
        layout.addWidget(options_group)
        
        # Import type selection
        type_group = QGroupBox("Content Type")
        type_layout = QVBoxLayout(type_group)
        
        self.auto_detect_radio = QRadioButton("Auto-detect content type")
        self.auto_detect_radio.setChecked(True)
        type_layout.addWidget(self.auto_detect_radio)
        
        self.article_radio = QRadioButton("Article/Blog post")
        type_layout.addWidget(self.article_radio)
        
        self.academic_radio = QRadioButton("Academic paper")
        type_layout.addWidget(self.academic_radio)
        
        self.documentation_radio = QRadioButton("Documentation")
        type_layout.addWidget(self.documentation_radio)
        
        layout.addWidget(type_group)
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Set initial focus
        self.url_line.setFocus() 