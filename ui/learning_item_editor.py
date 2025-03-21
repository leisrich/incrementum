# ui/learning_item_editor.py

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QComboBox, QSpinBox,
    QGroupBox, QFormLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QMessageBox,
    QRadioButton, QButtonGroup, QCheckBox, QDoubleSpinBox,
    QPlainTextEdit, QAbstractItemView, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QIcon
# Import sip for safe widget checking
from PyQt6 import sip

from core.knowledge_base.models import Extract, LearningItem, ReviewLog
from core.content_extractor.nlp_extractor import NLPExtractor

logger = logging.getLogger(__name__)

class LearningItemEditor(QWidget):
    """Widget for editing learning items."""
    
    itemSaved = pyqtSignal(int)  # item_id
    itemDeleted = pyqtSignal(int)  # item_id
    
    def __init__(self, db_session, item_id=None, extract_id=None):
        super().__init__()
        
        self.db_session = db_session
        self.item_id = item_id
        self.extract_id = extract_id
        
        self.item = None
        self.extract = None
        self.nlp_extractor = NLPExtractor(db_session)
        
        # Load data
        self._load_data()
        
        # Create UI
        self._create_ui()
        
        # Load item data if editing
        if self.item:
            self._load_item_data()
    
    def _load_data(self):
        """Load item and extract data."""
        if self.item_id:
            # Editing existing item
            self.item = self.db_session.query(LearningItem).get(self.item_id)
            if not self.item:
                logger.error(f"Learning item not found: {self.item_id}")
                return
            
            self.extract = self.item.extract
            self.extract_id = self.extract.id if self.extract else None
        elif self.extract_id:
            # Creating new item from extract
            self.extract = self.db_session.query(Extract).get(self.extract_id)
            if not self.extract:
                logger.error(f"Extract not found: {self.extract_id}")
                return
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Header
        if self.item:
            title = "Edit Learning Item"
        else:
            title = "Create Learning Item"
        
        header_label = QLabel(f"<h2>{title}</h2>")
        main_layout.addWidget(header_label)
        
        # Extract preview (if available)
        if self.extract:
            extract_group = QGroupBox("Source Extract")
            extract_layout = QVBoxLayout(extract_group)
            
            extract_text = QTextEdit()
            extract_text.setReadOnly(True)
            extract_text.setText(self.extract.content)
            extract_text.setMaximumHeight(150)
            extract_layout.addWidget(extract_text)
            
            main_layout.addWidget(extract_group)
        
        # Item type selection (only for new items)
        if not self.item:
            type_group = QGroupBox("Item Type")
            type_layout = QHBoxLayout(type_group)
            
            self.type_group = QButtonGroup(self)
            
            self.qa_radio = QRadioButton("Question-Answer")
            self.qa_radio.setChecked(True)
            self.type_group.addButton(self.qa_radio)
            type_layout.addWidget(self.qa_radio)
            
            self.cloze_radio = QRadioButton("Cloze Deletion")
            self.type_group.addButton(self.cloze_radio)
            type_layout.addWidget(self.cloze_radio)
            
            # Connect signals
            self.qa_radio.toggled.connect(self._on_type_changed)
            self.cloze_radio.toggled.connect(self._on_type_changed)
            
            main_layout.addWidget(type_group)
        
        # Item content
        content_tabs = QTabWidget()
        
        # Basic tab
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        
        # Item content form
        form_layout = QFormLayout()
        
        # Question
        question_label = QLabel("Question:")
        self.question_edit = QTextEdit()
        form_layout.addRow(question_label, self.question_edit)
        
        # Answer
        answer_label = QLabel("Answer:")
        self.answer_edit = QTextEdit()
        form_layout.addRow(answer_label, self.answer_edit)
        
        # Priority
        priority_layout = QHBoxLayout()
        priority_label = QLabel("Priority:")
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 5)
        self.priority_spin.setValue(3)
        priority_layout.addWidget(priority_label)
        priority_layout.addWidget(self.priority_spin)
        priority_layout.addStretch()
        form_layout.addRow("Priority:", priority_layout)
        
        basic_layout.addLayout(form_layout)
        
        # Auto-generation frame
        self.auto_frame = QGroupBox("Auto-generation")
        self.auto_frame.setCheckable(True)
        self.auto_frame.setChecked(False)
        auto_layout = QVBoxLayout(self.auto_frame)
        
        # Generation mode
        mode_layout = QHBoxLayout()
        mode_label = QLabel("Generation Mode:")
        self.auto_mode_combo = QComboBox()
        self.auto_mode_combo.addItem("Template-based", "template")
        self.auto_mode_combo.addItem("AI-assisted", "ai")
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.auto_mode_combo)
        auto_layout.addLayout(mode_layout)
        
        # Provider selection (only visible in AI mode)
        self.provider_container = QWidget()
        provider_layout = QHBoxLayout(self.provider_container)
        provider_layout.setContentsMargins(0, 0, 0, 0)
        
        provider_label = QLabel("AI Provider:")
        self.provider_combo = QComboBox()
        
        # Add settings button
        self.api_settings_btn = QPushButton("⚙️")
        self.api_settings_btn.setToolTip("Open API settings")
        self.api_settings_btn.setMaximumWidth(30)
        self.api_settings_btn.clicked.connect(self._on_open_api_settings)
        
        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.provider_combo)
        provider_layout.addWidget(self.api_settings_btn)
        auto_layout.addWidget(self.provider_container)
        
        # Populate providers from AI_PROVIDERS
        try:
            from core.document_processor.summarizer import AI_PROVIDERS
            for provider_id, provider_info in AI_PROVIDERS.items():
                self.provider_combo.addItem(provider_info["name"], provider_id)
        except Exception:
            # Fallback if we can't import AI_PROVIDERS
            self.provider_combo.addItem("OpenAI", "openai")
            self.provider_combo.addItem("Claude", "anthropic")
            self.provider_combo.addItem("OpenRouter", "openrouter")
            self.provider_combo.addItem("Google Gemini", "google")
        
        # Count selection
        count_layout = QHBoxLayout()
        count_label = QLabel("Number of items:")
        self.question_count = QSpinBox()
        self.question_count.setMinimum(1)
        self.question_count.setMaximum(20)
        self.question_count.setValue(5)
        count_layout.addWidget(count_label)
        count_layout.addWidget(self.question_count)
        count_layout.addStretch()
        auto_layout.addLayout(count_layout)
        
        # Generation button
        generate_layout = QHBoxLayout()
        generate_layout.addStretch()
        self.generate_btn = QPushButton("Generate")
        generate_layout.addWidget(self.generate_btn)
        auto_layout.addLayout(generate_layout)
        
        # Results table
        self.generation_results = QTableWidget()
        self.generation_results.setColumnCount(3)
        self.generation_results.setHorizontalHeaderLabels(["Use", "Question", "Answer"])
        self.generation_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.generation_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.generation_results.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.generation_results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.generation_results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.generation_results.setColumnWidth(0, 40)
        auto_layout.addWidget(self.generation_results)
        
        # Add more button
        more_layout = QHBoxLayout()
        more_layout.addStretch()
        self.add_selected_btn = QPushButton("Add Selected Items")
        more_layout.addWidget(self.add_selected_btn)
        auto_layout.addLayout(more_layout)
        
        basic_layout.addWidget(self.auto_frame)
        
        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Review history
        self.show_history_btn = QPushButton("Show Review History")
        button_layout.addWidget(self.show_history_btn)
        
        # Save and delete buttons
        if self.item_id:
            # Edit mode
            self.save_btn = QPushButton("Save Changes")
            self.delete_btn = QPushButton("Delete Item")
            button_layout.addWidget(self.save_btn)
            button_layout.addWidget(self.delete_btn)
        else:
            # Create mode
            self.save_btn = QPushButton("Create Item")
            button_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(button_layout)
        
        # Connect signals
        self.qa_radio.toggled.connect(self._on_type_changed)
        self.auto_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.generate_btn.clicked.connect(self._on_generate)
        self.add_selected_btn.clicked.connect(self._on_generate_more)
        self.save_btn.clicked.connect(self._on_save)
        self.generation_results.itemClicked.connect(self._on_result_selected)
        self.api_settings_btn.clicked.connect(self._on_open_api_settings)
        
        if self.item_id:
            self.delete_btn.clicked.connect(self._on_delete)
            self.show_history_btn.clicked.connect(self._on_show_history)
        
        # Initial UI state
        self._on_type_changed()
        self._on_mode_changed()
        
        # Hide history button if no item yet
        if not self.item_id:
            self.show_history_btn.setVisible(False)
    
    def _load_item_data(self):
        """Load existing item data into UI."""
        if not self.item:
            return
        
        # Load basic data
        self.question_edit.setText(self.item.question)
        self.answer_edit.setText(self.item.answer)
        self.priority_spin.setValue(self.item.priority)
        
        # Load advanced data
        if hasattr(self, 'interval_spin'):
            self.interval_spin.setValue(self.item.interval)
            self.repetitions_spin.setValue(self.item.repetitions)
            self.easiness_spin.setValue(self.item.easiness)
        
        # Load review history
        if hasattr(self, 'history_table'):
            self._load_review_history()
    
    def _load_review_history(self):
        """Load review history for the item."""
        if not self.item:
            return
        
        # Clear table
        self.history_table.setRowCount(0)
        
        # Get review logs
        logs = self.db_session.query(ReviewLog).filter(
            ReviewLog.learning_item_id == self.item.id
        ).order_by(ReviewLog.review_date.desc()).all()
        
        # Add rows
        for i, log in enumerate(logs):
            self.history_table.insertRow(i)
            
            # Date
            date_item = QTableWidgetItem(log.review_date.strftime("%Y-%m-%d %H:%M"))
            self.history_table.setItem(i, 0, date_item)
            
            # Grade
            grade_item = QTableWidgetItem(str(log.grade))
            
            # Color based on grade
            if log.grade >= 4:
                grade_item.setBackground(QColor(200, 255, 200))  # Light green
            elif log.grade >= 3:
                grade_item.setBackground(QColor(255, 255, 200))  # Light yellow
            else:
                grade_item.setBackground(QColor(255, 200, 200))  # Light red
                
            self.history_table.setItem(i, 1, grade_item)
            
            # Response time
            if log.response_time:
                time_str = f"{log.response_time / 1000:.1f} sec"
            else:
                time_str = "-"
            time_item = QTableWidgetItem(time_str)
            self.history_table.setItem(i, 2, time_item)
            
            # Interval
            interval_item = QTableWidgetItem(f"{log.scheduled_interval} days")
            self.history_table.setItem(i, 3, interval_item)
    
    @pyqtSlot()
    def _on_type_changed(self):
        """Handle item type selection change."""
        try:
            # First check that our widgets are valid
            if not hasattr(self, 'question_edit') or not self._is_widget_valid(self.question_edit):
                return
                
            if not hasattr(self, 'answer_edit') or not self._is_widget_valid(self.answer_edit):
                return
        
            if hasattr(self, 'qa_radio') and self.qa_radio.isChecked():
                # Question-Answer mode
                self.question_edit.setPlaceholderText("Enter the question")
                self.answer_edit.setPlaceholderText("Enter the answer")
            else:
                # Cloze deletion mode
                self.question_edit.setPlaceholderText("Enter text with [...] for cloze deletion")
                self.answer_edit.setPlaceholderText("Enter the text that goes in place of [...]")
        except RuntimeError as e:
            logger.warning(f"Error in _on_type_changed: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error in _on_type_changed: {e}")
    
    @pyqtSlot()
    def _on_mode_changed(self):
        """Handle content generation mode change."""
        # Show/hide provider selection based on mode
        if hasattr(self, 'auto_mode_combo') and hasattr(self, 'provider_container'):
            use_ai = self.auto_mode_combo.currentData() == "ai"
            self.provider_container.setVisible(use_ai)
    
    @pyqtSlot()
    def _on_generate(self):
        """Handle generate button click."""
        # Check if there's an extract
        if not self.extract:
            QMessageBox.warning(
                self, "No Extract", 
                "Please select an extract first."
            )
            return
        
        # Clear previous results
        self.generation_results.setRowCount(0)
        
        # Get generation mode
        mode = self.auto_mode_combo.currentData()
        count = self.question_count.value()
        
        # Generate content based on mode
        if mode == "ai":
            # Get API configuration
            api_config = self._get_api_config()
            
            if not api_config or not api_config.get('api_key'):
                # Prompt to set API key
                self._prompt_for_api_key()
                api_config = self._get_api_config()
                
                # If still no API key, fall back to template-based
                if not api_config or not api_config.get('api_key'):
                    provider_name = self.provider_combo.currentText()
                    QMessageBox.warning(
                        self, "No API Key", 
                        f"No API key set for {provider_name}. The key may not have been saved correctly.\n\n"
                        f"Please go to Settings > AI/API Settings to set your {provider_name} API key, "
                        f"or try entering it again. Falling back to template-based generation."
                    )
                    items = self._generate_with_templates(count)
                else:
                    # AI-assisted generation with the configured provider
                    try:
                        items = self._generate_with_ai(count, api_config)
                    except Exception as e:
                        logger.exception(f"Error generating with AI: {e}")
                        provider_name = self.provider_combo.currentText()
                        QMessageBox.warning(
                            self, "AI Generation Error", 
                            f"An error occurred when using {provider_name} API: {str(e)}\n\n"
                            f"Please verify your API key is correct. Falling back to template-based generation."
                        )
                        items = self._generate_with_templates(count)
            else:
                # AI-assisted generation with the configured provider
                try:
                    items = self._generate_with_ai(count, api_config)
                except Exception as e:
                    logger.exception(f"Error generating with AI: {e}")
                    provider_name = self.provider_combo.currentText()
                    QMessageBox.warning(
                        self, "AI Generation Error", 
                        f"An error occurred when using {provider_name} API: {str(e)}\n\n"
                        f"Please verify your API key is correct. Falling back to template-based generation."
                    )
                    items = self._generate_with_templates(count)
        else:
            # Template-based generation
            items = self._generate_with_templates(count)
        
        # Show results
        for i, item in enumerate(items):
            self.generation_results.insertRow(i)
            
            # Use checkbox
            use_check = QTableWidgetItem()
            use_check.setCheckState(Qt.CheckState.Checked)
            self.generation_results.setItem(i, 0, use_check)
            
            # Question
            question_item = QTableWidgetItem(item.question)
            question_item.setData(Qt.ItemDataRole.UserRole, item.id)
            self.generation_results.setItem(i, 1, question_item)
            
            # Answer
            answer_item = QTableWidgetItem(item.answer)
            self.generation_results.setItem(i, 2, answer_item)
    
    def _generate_with_ai(self, count, api_config):
        """Generate items using AI with the specified configuration."""
        if self.qa_radio.isChecked():
            return self.nlp_extractor.generate_qa_pairs(self.extract_id, max_pairs=count, ai_config=api_config)
        else:
            return self.nlp_extractor.generate_cloze_deletions(self.extract_id, max_items=count, ai_config=api_config)
    
    def _generate_with_templates(self, count):
        """Generate items using templates."""
        if self.qa_radio.isChecked():
            return self._generate_template_qa(count)
        else:
            return self._generate_template_cloze(count)
    
    def _get_api_config(self):
        """Get API configuration from settings for the selected provider."""
        try:
            from core.utils.settings_manager import SettingsManager
            from core.document_processor.summarizer import AI_PROVIDERS
            
            settings = SettingsManager()
            
            # Get selected provider
            provider_id = self.provider_combo.currentData()
            
            # Get API key for selected provider
            setting_key = AI_PROVIDERS[provider_id]["setting_key"]
            # API keys are stored in the "api" section, not "ai"
            api_key = settings.get_setting("api", setting_key, "")
            
            # Get saved model for this provider or use default
            model_setting_key = f"{provider_id}_model"
            model = settings.get_setting("api", model_setting_key, AI_PROVIDERS[provider_id]["default_model"])
            
            # If no API key, return empty config
            if not api_key:
                logger.warning(f"No API key found for {provider_id}. Setting key: {setting_key}")
                return {}
            
            return {
                "provider": provider_id,
                "api_key": api_key,
                "model": model
            }
            
        except Exception as e:
            logger.exception(f"Error getting API configuration: {e}")
            return {}
    
    def _prompt_for_api_key(self):
        """Prompt user to enter API key for the selected provider."""
        try:
            from core.utils.settings_manager import SettingsManager
            from core.document_processor.summarizer import AI_PROVIDERS
            
            settings = SettingsManager()
            
            provider_id = self.provider_combo.currentData()
            provider_name = self.provider_combo.currentText()
            
            setting_key = AI_PROVIDERS[provider_id]["setting_key"]
            # API keys are stored in the "api" section, not "ai"
            current_key = settings.get_setting("api", setting_key, "")
            
            # Mask key for display
            masked_key = "****" + current_key[-4:] if current_key and len(current_key) > 4 else ""
            hint_text = f"Current: {masked_key}" if masked_key else "No API key set"
            
            from PyQt6.QtWidgets import QInputDialog, QLineEdit
            
            api_key, ok = QInputDialog.getText(
                self, f"Set {provider_name} API Key", 
                f"Enter your {provider_name} API key for AI-powered generation:\n{hint_text}",
                QLineEdit.EchoMode.Password
            )
            
            if ok and api_key:
                # Save to settings
                settings.set_setting("ai", "provider", provider_id)
                
                # Save API key to the "api" section, not "ai"
                settings.set_setting("api", setting_key, api_key)
                
                # Save default model to "api" section
                from core.document_processor.summarizer import AI_PROVIDERS
                model = AI_PROVIDERS[provider_id]["default_model"]
                model_setting_key = f"{provider_id}_model"
                settings.set_setting("api", model_setting_key, model)
                
                # Save settings to disk
                settings.save_settings()
                
                # Log success
                logger.info(f"Saved API key for {provider_name} (key: {setting_key})")
                
                # Show confirmation
                QMessageBox.information(
                    self, "API Key Set", 
                    f"Your {provider_name} API key has been saved successfully."
                )
                
                return True
            
        except Exception as e:
            logger.exception(f"Error setting API key: {e}")
        
        return False
    
    @pyqtSlot(QTableWidgetItem)
    def _on_result_selected(self, item):
        """Handle selection of a generated item."""
        try:
            # First check that the required widgets exist and are valid
            if not self._is_widget_valid(self.question_edit) or not self._is_widget_valid(self.answer_edit):
                logger.warning("Cannot select result: text editors are not valid")
                return
                
            if not self._is_widget_valid(self.generation_results):
                logger.warning("Cannot select result: generation results table is not valid")
                return
                
            if item.column() in [1, 2]:  # Question or answer column
                row = item.row()
                
                # Get question and answer items
                question_item = self.generation_results.item(row, 1)
                answer_item = self.generation_results.item(row, 2)
                
                if not question_item or not answer_item:
                    logger.warning(f"Result row {row} has missing items")
                    return
                
                # Get question and answer text
                question = question_item.text()
                answer = answer_item.text()
                
                # Set in the editor
                self.question_edit.setText(question)
                self.answer_edit.setText(answer)
        except RuntimeError as e:
            logger.warning(f"Error in _on_result_selected: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error in _on_result_selected: {e}")
    
    @pyqtSlot()
    def _on_generate_more(self):
        """Handle generate more button."""
        try:
            # Check if widgets are valid
            if not hasattr(self, 'generation_results') or not self._is_widget_valid(self.generation_results):
                logger.warning("Cannot generate more: results table is not valid")
                return
                
            if not hasattr(self, 'priority_spin') or not self._is_widget_valid(self.priority_spin):
                logger.warning("Cannot generate more: priority spinner is not valid")
                return
        
            # Check selected items
            selected_items = []
            
            for i in range(self.generation_results.rowCount()):
                use_check = self.generation_results.item(i, 0)
                
                if not use_check:
                    continue
                
                if use_check.checkState() == Qt.CheckState.Checked:
                    question_item = self.generation_results.item(i, 1)
                    answer_item = self.generation_results.item(i, 2)
                    
                    if not question_item or not answer_item:
                        continue
                        
                    question = question_item.text()
                    answer = answer_item.text()
                    
                    selected_items.append({
                        'question': question,
                        'answer': answer
                    })
            
            # Save selected items
            saved_count = 0
            for item_data in selected_items:
                # Create new item
                item = LearningItem(
                    extract_id=self.extract_id,
                    item_type='qa' if hasattr(self, 'qa_radio') and self.qa_radio.isChecked() else 'cloze',
                    question=item_data['question'],
                    answer=item_data['answer'],
                    priority=self.priority_spin.value(),
                    created_date=datetime.utcnow()
                )
                
                self.db_session.add(item)
                saved_count += 1
            
            # Commit
            self.db_session.commit()
            
            # Mark extract as processed
            if saved_count > 0 and self.extract:
                self.extract.processed = True
                self.db_session.commit()
            
            # Show message
            QMessageBox.information(
                self, "Items Created", 
                f"Created {saved_count} learning items successfully."
            )
            
            # Generate more
            self._on_generate()
            
        except RuntimeError as e:
            logger.warning(f"Error in _on_generate_more: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"An error occurred when saving items: {str(e)}"
            )
        except Exception as e:
            logger.exception(f"Unexpected error in _on_generate_more: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to save items: {str(e)}"
            )
    
    def _is_widget_valid(self, widget):
        """Safely check if a widget is valid and usable.
        
        Args:
            widget: The widget to check
            
        Returns:
            bool: True if the widget is valid and can be used
        """
        return (widget is not None and 
                not sip.isdeleted(widget) and 
                hasattr(widget, 'isVisible'))
                
    @pyqtSlot()
    def _on_save(self):
        """Save the learning item."""
        try:
            # Validate content - with safety checks for deleted widgets
            if not hasattr(self, 'question_edit') or not self._is_widget_valid(self.question_edit):
                QMessageBox.warning(
                    self, "Widget Error", 
                    "The question editor has been deleted or is invalid. Please try again or reopen the dialog."
                )
                return
                
            if not hasattr(self, 'answer_edit') or not self._is_widget_valid(self.answer_edit):
                QMessageBox.warning(
                    self, "Widget Error", 
                    "The answer editor has been deleted or is invalid. Please try again or reopen the dialog."
                )
                return
                
            question = self.question_edit.toPlainText().strip()
            answer = self.answer_edit.toPlainText().strip()
            
            if not question:
                QMessageBox.warning(
                    self, "Missing Question", 
                    "Please enter a question."
                )
                return
            
            if not answer:
                QMessageBox.warning(
                    self, "Missing Answer", 
                    "Please enter an answer."
                )
                return
            
            if not self.extract_id:
                QMessageBox.warning(
                    self, "Missing Extract", 
                    "No source extract specified."
                )
                return
            
            if self.item:
                # Update existing item
                self.item.question = question
                self.item.answer = answer
                self.item.priority = self.priority_spin.value()
                
                # Update SR parameters if requested
                if hasattr(self, 'reset_sr_check') and self.reset_sr_check.isChecked():
                    self.item.interval = 0
                    self.item.repetitions = 0
                    self.item.easiness = 2.5
                    self.item.next_review = None
                elif hasattr(self, 'interval_spin'):
                    self.item.interval = self.interval_spin.value()
                    self.item.repetitions = self.repetitions_spin.value()
                    self.item.easiness = self.easiness_spin.value()
                
                self.db_session.commit()
                
                # Emit signal
                self.itemSaved.emit(self.item.id)
                
                QMessageBox.information(
                    self, "Item Updated", 
                    "Learning item updated successfully."
                )
            else:
                # Create new item
                item = LearningItem(
                    extract_id=self.extract_id,
                    item_type='qa' if not hasattr(self, 'qa_radio') or self.qa_radio.isChecked() else 'cloze',
                    question=question,
                    answer=answer,
                    priority=self.priority_spin.value(),
                    created_date=datetime.utcnow()
                )
                
                self.db_session.add(item)
                self.db_session.commit()
                
                # Mark extract as processed
                if self.extract:
                    self.extract.processed = True
                    self.db_session.commit()
                
                # Emit signal
                self.itemSaved.emit(item.id)
                
                QMessageBox.information(
                    self, "Item Created", 
                    "Learning item created successfully."
                )
                
                # Clear form for next item
                if hasattr(self, 'question_edit') and self.question_edit is not None:
                    self.question_edit.clear()
                if hasattr(self, 'answer_edit') and self.answer_edit is not None:
                    self.answer_edit.clear()
                
        except RuntimeError as e:
            if "has been deleted" in str(e):
                logger.exception("UI widget has been deleted prematurely")
                QMessageBox.warning(
                    self, "Interface Error", 
                    "A UI component was deleted unexpectedly. Please try again."
                )
            else:
                logger.exception(f"Error saving learning item: {e}")
                QMessageBox.warning(
                    self, "Error", 
                    f"Failed to save learning item: {str(e)}"
                )
        except Exception as e:
            logger.exception(f"Error saving learning item: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Failed to save learning item: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_delete(self):
        """Delete the learning item."""
        if not self.item:
            return
        
        # Confirmation dialog
        reply = QMessageBox.question(
            self, "Confirm Delete", 
            "Are you sure you want to delete this learning item?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Delete item
                item_id = self.item.id
                self.db_session.delete(self.item)
                self.db_session.commit()
                
                # Emit signal
                self.itemDeleted.emit(item_id)
                
                QMessageBox.information(
                    self, "Item Deleted", 
                    "Learning item deleted successfully."
                )
                
            except Exception as e:
                logger.exception(f"Error deleting learning item: {e}")
                QMessageBox.warning(
                    self, "Error", 
                    f"Failed to delete learning item: {str(e)}"
                )
    
    @pyqtSlot()
    def _on_open_api_settings(self):
        """Open the settings dialog to the API section."""
        try:
            from core.utils.settings_manager import SettingsManager
            from ui.settings_dialog import SettingsDialog
            
            settings = SettingsManager()
            dialog = SettingsDialog(settings, self)
            
            # Try to select API tab if available
            if hasattr(dialog, 'tabWidget') and dialog.tabWidget.count() > 4:
                dialog.tabWidget.setCurrentIndex(4)  # API tab is typically the 5th tab
                
            result = dialog.exec()
            
            if result == QDialog.DialogCode.Accepted:
                # Refresh API config
                provider_id = self.provider_combo.currentData()
                provider_name = self.provider_combo.currentText()
                
                # Show confirmation if API key is now set
                from core.document_processor.summarizer import AI_PROVIDERS
                setting_key = AI_PROVIDERS[provider_id]["setting_key"]
                api_key = settings.get_setting("api", setting_key, "")
                
                if api_key:
                    QMessageBox.information(
                        self, "API Key Set", 
                        f"Your {provider_name} API key has been saved successfully."
                    )
                
        except Exception as e:
            logger.exception(f"Error opening settings dialog: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error opening settings dialog: {str(e)}"
            )

    def _generate_template_qa(self, count: int) -> List[LearningItem]:
        """Generate template-based question-answer pairs."""
        if not self.extract:
            return []
        
        # Split extract content into sentences
        import nltk
        try:
            sentences = nltk.sent_tokenize(self.extract.content)
        except:
            # Fallback if NLTK not available
            sentences = self.extract.content.split('. ')
        
        # Simple templates
        templates = [
            "What is {}?",
            "Explain {}.",
            "Define {}.",
            "Describe {}.",
            "What are the characteristics of {}?",
            "How would you explain {}?"
        ]
        
        # Generate items
        items = []
        
        # Extract key terms
        key_concepts = self.nlp_extractor.identify_key_concepts(
            self.extract.content, num_concepts=min(count*2, 10)
        )
        
        import random
        
        for i in range(min(count, len(key_concepts))):
            concept = key_concepts[i]
            term = concept['text']
            
            # Find a sentence containing this term
            context = ""
            for sentence in sentences:
                if term.lower() in sentence.lower():
                    context = sentence
                    break
            
            if not context:
                context = self.extract.content[:200] + "..."
            
            # Create question using template
            template = random.choice(templates)
            question = template.format(term)
            
            # Create item
            item = LearningItem(
                extract_id=self.extract_id,
                item_type='qa',
                question=question,
                answer=context,
                priority=self.extract.priority
            )
            
            items.append(item)
        
        return items

    def _generate_template_cloze(self, count: int) -> List[LearningItem]:
        """Generate template-based cloze deletions."""
        if not self.extract:
            return []
        
        # Split extract content into sentences
        import nltk
        try:
            sentences = nltk.sent_tokenize(self.extract.content)
        except:
            # Fallback if NLTK not available
            sentences = self.extract.content.split('. ')
        
        # Generate items
        items = []
        
        # Extract key terms
        key_concepts = self.nlp_extractor.identify_key_concepts(
            self.extract.content, num_concepts=min(count*3, 15)
        )
        
        import random
        
        # Shuffle sentences for variety
        random.shuffle(sentences)
        
        for i in range(min(count, len(key_concepts), len(sentences))):
            concept = key_concepts[i]
            term = concept['text']
            
            # Find a sentence containing this term
            context = ""
            for sentence in sentences:
                if term.lower() in sentence.lower():
                    context = sentence
                    sentences.remove(sentence)  # Don't reuse this sentence
                    break
            
            if not context:
                continue
            
            # Create cloze by replacing the term
            cloze_text = context.replace(term, "[...]")
            
            # Create item
            item = LearningItem(
                extract_id=self.extract_id,
                item_type='cloze',
                question=cloze_text,
                answer=term,
                priority=self.extract.priority
            )
            
            items.append(item)
        
        return items

    def _safe_disconnect(self, obj, signal_name=None):
        """Safely disconnect signals from an object.
        
        Args:
            obj: The Qt object
            signal_name: Optional specific signal name to disconnect
                       If None, disconnect all signals
        """
        if obj is None or not hasattr(obj, 'disconnect') or sip.isdeleted(obj):
            return
            
        try:
            if signal_name:
                # Disconnect specific signal
                getattr(obj, signal_name).disconnect()
            else:
                # Disconnect all signals
                obj.disconnect()
        except (TypeError, RuntimeError) as e:
            # It's normal for this to fail if signals weren't connected
            logger.debug(f"Signal disconnect info: {e}")
        except Exception as e:
            logger.warning(f"Error disconnecting signals from {obj}: {e}")
            
    def closeEvent(self, event):
        """Handle widget close event."""
        # Disconnect signals to prevent accessing deleted widgets
        try:
            # Disconnect all signals first to prevent callbacks accessing deleted widgets
            if hasattr(self, 'auto_mode_combo') and not sip.isdeleted(self.auto_mode_combo):
                self._safe_disconnect(self.auto_mode_combo, 'currentIndexChanged')
            if hasattr(self, 'generate_btn') and not sip.isdeleted(self.generate_btn):
                self._safe_disconnect(self.generate_btn, 'clicked')
            if hasattr(self, 'add_selected_btn') and not sip.isdeleted(self.add_selected_btn):
                self._safe_disconnect(self.add_selected_btn, 'clicked')
            if hasattr(self, 'save_btn') and not sip.isdeleted(self.save_btn):
                self._safe_disconnect(self.save_btn, 'clicked')
            if hasattr(self, 'generation_results') and not sip.isdeleted(self.generation_results):
                self._safe_disconnect(self.generation_results, 'itemClicked')
            if hasattr(self, 'api_settings_btn') and not sip.isdeleted(self.api_settings_btn):
                self._safe_disconnect(self.api_settings_btn, 'clicked')
            if hasattr(self, 'qa_radio') and not sip.isdeleted(self.qa_radio):
                self._safe_disconnect(self.qa_radio, 'toggled')
            if hasattr(self, 'delete_btn') and not sip.isdeleted(self.delete_btn):
                self._safe_disconnect(self.delete_btn, 'clicked')
            if hasattr(self, 'show_history_btn') and not sip.isdeleted(self.show_history_btn):
                self._safe_disconnect(self.show_history_btn, 'clicked')
                    
        except Exception as e:
            logger.warning(f"Error disconnecting signals: {e}")
            
        # Set a flag to indicate we're closing to prevent further widget access
        self._is_closing = True
            
        # Perform cleanup before closing
        try:
            # Nullify all QWidget attributes to prevent access after deletion
            widget_attrs = [
                'question_edit', 'answer_edit', 'priority_spin', 
                'generation_results', 'qa_radio', 'cloze_radio',
                'auto_mode_combo', 'provider_combo', 'api_settings_btn',
                'generate_btn', 'add_selected_btn', 'save_btn',
                'delete_btn', 'show_history_btn'
            ]
            
            for attr in widget_attrs:
                if hasattr(self, attr):
                    setattr(self, attr, None)
                    
        except Exception as e:
            logger.warning(f"Error cleaning up widgets: {e}")
            
        # Accept the close event
        event.accept()

    def __del__(self):
        """Destructor to ensure proper cleanup."""
        try:
            # Set a flag to indicate we're being destroyed
            self._is_destroyed = True
            
            # Disconnect all signals first
            if hasattr(self, '_safe_disconnect'):
                # Get all attributes that might be Qt objects with signals
                for attr_name in list(self.__dict__.keys()):
                    if attr_name.startswith('_'):
                        continue
                    
                    try:
                        obj = getattr(self, attr_name)
                        if obj is not None and hasattr(obj, 'disconnect') and not sip.isdeleted(obj):
                            obj.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    except Exception as e:
                        logger.debug(f"Error disconnecting {attr_name}: {e}")
            
            # Clean up Qt widgets to prevent access after deletion
            widget_attrs = [
                'question_edit', 'answer_edit', 'priority_spin', 
                'generation_results', 'qa_radio', 'cloze_radio',
                'auto_mode_combo', 'provider_combo', 'api_settings_btn',
                'generate_btn', 'add_selected_btn', 'save_btn',
                'delete_btn', 'show_history_btn'
            ]
            
            for attr in widget_attrs:
                if hasattr(self, attr):
                    setattr(self, attr, None)
                    
        except Exception as e:
            # Ignore errors during cleanup but log them
            logger.debug(f"Error during destruction: {e}")
