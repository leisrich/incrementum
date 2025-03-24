from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QTextEdit, QGroupBox,
    QFormLayout, QSpinBox, QTabWidget, QWidget,
    QCheckBox, QRadioButton, QMessageBox, QProgressBar,
    QDialogButtonBox, QSlider
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QThread
from PyQt6.QtGui import QFont

from core.ai_services.llm_service import LLMServiceFactory
from core.ai_services.content_processor import ContentProcessor
from core.utils.settings_manager import SettingsManager


class ProcessContentThread(QThread):
    """Background thread for processing content with LLMs."""
    
    resultReady = pyqtSignal(str)
    errorOccurred = pyqtSignal(str)
    progressUpdate = pyqtSignal(str)
    
    def __init__(self, content_processor, content, operation, options=None):
        super().__init__()
        self.content_processor = content_processor
        self.content = content
        self.operation = operation
        self.options = options or {}
        self.is_running = True
    
    def run(self):
        try:
            self.progressUpdate.emit("Processing content...")
            
            result = ""
            if self.operation == "summary":
                max_length = self.options.get("max_length", 500)
                focus_areas = self.options.get("focus_areas", "")
                result = self.content_processor.generate_summary(
                    self.content, max_length=max_length, focus_areas=focus_areas
                )
                
            elif self.operation == "article":
                style = self.options.get("style", "informative")
                length = self.options.get("length", "medium")
                tone = self.options.get("tone", "neutral")
                result = self.content_processor.generate_article(
                    self.content, style=style, length=length, tone=tone
                )
                
            elif self.operation == "key_points":
                num_points = self.options.get("num_points", 5)
                result = self.content_processor.extract_key_points(
                    self.content, num_points=num_points
                )
                
            elif self.operation == "questions":
                questions = self.options.get("questions", "")
                result = self.content_processor.answer_questions(
                    self.content, questions=questions
                )
            
            # Only emit if we're still running (not terminated)
            if self.is_running:
                self.resultReady.emit(result)
            
        except Exception as e:
            if self.is_running:
                self.errorOccurred.emit(f"Error processing content: {str(e)}")
    
    def stop(self):
        """Safely stop the thread"""
        self.is_running = False


class ContentProcessorDialog(QDialog):
    """Dialog for processing content with LLMs."""
    
    contentProcessed = pyqtSignal(str)  # Emit the processed content
    
    def __init__(self, content, settings_manager, parent=None):
        super().__init__(parent)
        
        self.content = content
        self.settings_manager = settings_manager
        self.processed_content = ""
        self.process_thread = None
        
        self.setWindowTitle("Process Web Content")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)
        
        self._create_ui()
        self._setup_llm_service()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Content preview
        preview_group = QGroupBox("Content Preview")
        preview_layout = QVBoxLayout(preview_group)
        
        self.content_preview = QTextEdit()
        self.content_preview.setReadOnly(True)
        self.content_preview.setPlainText(self.content[:2000] + "..." if len(self.content) > 2000 else self.content)
        preview_layout.addWidget(self.content_preview)
        
        content_stats = QLabel(f"Content length: {len(self.content)} characters, approximately {len(self.content.split())} words")
        preview_layout.addWidget(content_stats)
        
        main_layout.addWidget(preview_group)
        
        # LLM service selection
        service_layout = QHBoxLayout()
        
        service_layout.addWidget(QLabel("LLM Service:"))
        self.service_combo = QComboBox()
        self.service_combo.addItems(["OpenAI", "Gemini", "Claude", "OpenRouter", "Ollama"])
        
        # Set default from settings
        default_service = self.settings_manager.get_setting("api", "default_llm_service", "OpenAI")
        index = self.service_combo.findText(default_service)
        if index >= 0:
            self.service_combo.setCurrentIndex(index)
            
        self.service_combo.currentIndexChanged.connect(self._on_service_changed)
        service_layout.addWidget(self.service_combo)
        
        service_layout.addWidget(QLabel("Temperature:"))
        self.temperature_slider = QSlider(Qt.Orientation.Horizontal)
        self.temperature_slider.setRange(1, 10)
        self.temperature_slider.setValue(7)  # Default 0.7
        self.temperature_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.temperature_slider.setTickInterval(1)
        service_layout.addWidget(self.temperature_slider)
        
        self.temperature_label = QLabel("0.7")
        self.temperature_slider.valueChanged.connect(
            lambda value: self.temperature_label.setText(f"{value/10:.1f}")
        )
        service_layout.addWidget(self.temperature_label)
        
        main_layout.addLayout(service_layout)
        
        # Tabs for different processing options
        self.option_tabs = QTabWidget()
        
        # Summary tab
        self._create_summary_tab()
        
        # Article tab
        self._create_article_tab()
        
        # Key points tab
        self._create_key_points_tab()
        
        # Q&A tab
        self._create_qa_tab()
        
        main_layout.addWidget(self.option_tabs)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        self.process_button = QPushButton("Process Content")
        self.process_button.clicked.connect(self._on_process)
        button_layout.addWidget(self.process_button)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        
        button_layout.addWidget(button_box)
        main_layout.addLayout(button_layout)
        
        # Result preview
        result_group = QGroupBox("Result Preview")
        result_layout = QVBoxLayout(result_group)
        
        self.result_preview = QTextEdit()
        self.result_preview.setReadOnly(True)
        result_layout.addWidget(self.result_preview)
        
        main_layout.addWidget(result_group)
    
    def _create_summary_tab(self):
        """Create the summary options tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Summary length
        self.summary_length = QSpinBox()
        self.summary_length.setRange(100, 2000)
        self.summary_length.setValue(500)
        self.summary_length.setSuffix(" words")
        layout.addRow("Summary length:", self.summary_length)
        
        # Focus areas
        self.focus_areas = QTextEdit()
        self.focus_areas.setPlaceholderText("Enter specific aspects to focus on in the summary (optional)")
        self.focus_areas.setMaximumHeight(80)
        layout.addRow("Focus on:", self.focus_areas)
        
        self.option_tabs.addTab(tab, "Summary")
    
    def _create_article_tab(self):
        """Create the article options tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Article style
        self.article_style = QComboBox()
        self.article_style.addItems(["Informative", "Analytical", "Conversational", "Persuasive", "Narrative"])
        layout.addRow("Style:", self.article_style)
        
        # Article length
        self.article_length = QComboBox()
        self.article_length.addItems(["Short (300 words)", "Medium (800 words)", "Long (1500 words)"])
        self.article_length.setCurrentIndex(1)  # Medium by default
        layout.addRow("Length:", self.article_length)
        
        # Article tone
        self.article_tone = QComboBox()
        self.article_tone.addItems(["Neutral", "Formal", "Casual", "Professional", "Friendly"])
        layout.addRow("Tone:", self.article_tone)
        
        self.option_tabs.addTab(tab, "Article")
    
    def _create_key_points_tab(self):
        """Create the key points options tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        
        # Number of key points
        self.num_key_points = QSpinBox()
        self.num_key_points.setRange(3, 15)
        self.num_key_points.setValue(5)
        self.num_key_points.setSuffix(" points")
        layout.addRow("Number of key points:", self.num_key_points)
        
        self.option_tabs.addTab(tab, "Key Points")
    
    def _create_qa_tab(self):
        """Create the Q&A options tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        layout.addWidget(QLabel("Enter questions about the content:"))
        
        self.questions_edit = QTextEdit()
        self.questions_edit.setPlaceholderText("Enter one or more questions, each on a new line")
        layout.addWidget(self.questions_edit)
        
        self.option_tabs.addTab(tab, "Q&A")
    
    def _setup_llm_service(self):
        """Set up the appropriate LLM service."""
        service_name = self.service_combo.currentText().lower()
        self.llm_service = LLMServiceFactory.create_service(service_name, self.settings_manager)
        
        if not self.llm_service or not self.llm_service.is_configured():
            self.status_label.setText(f"Warning: {service_name} service is not properly configured")
            self.process_button.setEnabled(False)
        else:
            self.status_label.setText("Ready")
            self.process_button.setEnabled(True)
        
        self.content_processor = ContentProcessor(self.llm_service)
    
    @pyqtSlot(int)
    def _on_service_changed(self, index):
        """Handle LLM service change."""
        self._setup_llm_service()
    
    @pyqtSlot()
    def _on_process(self):
        """Handle process button click."""
        # Get current tab
        current_tab = self.option_tabs.currentWidget()
        current_tab_text = self.option_tabs.tabText(self.option_tabs.currentIndex()).lower()
        
        # Prepare options based on current tab
        options = {}
        operation = ""
        
        if current_tab_text == "summary":
            operation = "summary"
            options["max_length"] = self.summary_length.value()
            options["focus_areas"] = self.focus_areas.toPlainText()
            
        elif current_tab_text == "article":
            operation = "article"
            options["style"] = self.article_style.currentText().lower()
            options["length"] = self.article_length.currentText().split(" ")[0].lower()
            options["tone"] = self.article_tone.currentText().lower()
            
        elif current_tab_text == "key points":
            operation = "key_points"
            options["num_points"] = self.num_key_points.value()
            
        elif current_tab_text == "q&a":
            operation = "questions"
            options["questions"] = self.questions_edit.toPlainText()
            if not options["questions"]:
                QMessageBox.warning(self, "No Questions", "Please enter at least one question.")
                return
        
        # Get temperature
        temperature = self.temperature_slider.value() / 10.0
        
        # Clean up any existing thread
        self._cleanup_thread()
        
        # Set up the processing thread
        self.process_thread = ProcessContentThread(
            self.content_processor, self.content, operation, options
        )
        self.process_thread.resultReady.connect(self._on_processing_complete)
        self.process_thread.errorOccurred.connect(self._on_processing_error)
        self.process_thread.progressUpdate.connect(self._on_progress_update)
        
        # Update UI
        self.progress_bar.setVisible(True)
        self.process_button.setEnabled(False)
        self.status_label.setText("Processing content...")
        
        # Start processing
        self.process_thread.start()
    
    @pyqtSlot(str)
    def _on_processing_complete(self, result):
        """Handle completion of content processing."""
        self.progress_bar.setVisible(False)
        self.process_button.setEnabled(True)
        self.status_label.setText("Processing complete")
        
        # Store result
        self.processed_content = result
        
        # Update preview
        self.result_preview.setPlainText(result)
        
        # Enable OK button
        self.ok_button.setEnabled(True)
    
    @pyqtSlot(str)
    def _on_processing_error(self, error_message):
        """Handle processing error."""
        self.progress_bar.setVisible(False)
        self.process_button.setEnabled(True)
        self.status_label.setText("Error")
        
        QMessageBox.warning(self, "Processing Error", error_message)
    
    @pyqtSlot(str)
    def _on_progress_update(self, message):
        """Handle progress updates."""
        self.status_label.setText(message)
    
    def get_processed_content(self):
        """Get the processed content."""
        return self.processed_content
    
    def accept(self):
        """Override accept to emit the content processed signal."""
        if self.processed_content:
            self.contentProcessed.emit(self.processed_content)
        super().accept()
    
    def closeEvent(self, event):
        """Handle dialog close event."""
        self._cleanup_thread()
        super().closeEvent(event)
    
    def reject(self):
        """Handle dialog rejection."""
        self._cleanup_thread()
        super().reject()
    
    def _cleanup_thread(self):
        """Clean up any running threads."""
        if self.process_thread and self.process_thread.isRunning():
            # Stop the thread gracefully
            self.process_thread.stop()
            
            # Wait for it to finish (with timeout)
            if not self.process_thread.wait(1000):  # 1 second timeout
                self.process_thread.terminate()
                self.process_thread.wait() 