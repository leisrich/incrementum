# ui/learning_item_editor.py

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QComboBox, QSpinBox,
    QGroupBox, QFormLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QMessageBox,
    QRadioButton, QButtonGroup, QCheckBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor

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
        priority_label = QLabel("Priority:")
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 100)
        self.priority_spin.setValue(50)  # Default
        form_layout.addRow(priority_label, self.priority_spin)
        
        basic_layout.addLayout(form_layout)
        
        # Content generator (for new items)
        if not self.item and self.extract:
            generator_group = QGroupBox("Content Generation")
            generator_layout = QVBoxLayout(generator_group)
            
            # Generation options
            options_layout = QHBoxLayout()
            
            # Generation mode
            self.auto_mode_combo = QComboBox()
            self.auto_mode_combo.addItem("AI-assisted generation", "ai")
            self.auto_mode_combo.addItem("Template-based generation", "template")
            options_layout.addWidget(self.auto_mode_combo)
            
            # AI Provider selection (only show when AI mode is selected)
            self.provider_label = QLabel("Provider:")
            options_layout.addWidget(self.provider_label)
            
            self.provider_combo = QComboBox()
            # We'll populate this from the AI_PROVIDERS in summarizer.py
            try:
                from core.document_processor.summarizer import AI_PROVIDERS
                for provider_id, provider_info in AI_PROVIDERS.items():
                    self.provider_combo.addItem(provider_info["name"], provider_id)
            except ImportError:
                # Fallback if we can't import AI_PROVIDERS
                self.provider_combo.addItem("OpenAI", "openai")
                self.provider_combo.addItem("Claude", "anthropic")
                self.provider_combo.addItem("OpenRouter", "openrouter")
                self.provider_combo.addItem("Google Gemini", "google")
            
            options_layout.addWidget(self.provider_combo)
            
            # Question count
            options_layout.addWidget(QLabel("Questions:"))
            self.question_count = QSpinBox()
            self.question_count.setRange(1, 10)
            self.question_count.setValue(3)
            options_layout.addWidget(self.question_count)
            
            # Generate button
            self.generate_button = QPushButton("Generate Questions")
            self.generate_button.clicked.connect(self._on_generate)
            options_layout.addWidget(self.generate_button)
            
            generator_layout.addLayout(options_layout)
            
            # Connect mode change to update UI
            self.auto_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
            
            # Results list
            self.generation_results = QTableWidget()
            self.generation_results.setColumnCount(3)
            self.generation_results.setHorizontalHeaderLabels(["Use", "Question", "Answer"])
            self.generation_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.generation_results.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            self.generation_results.itemDoubleClicked.connect(self._on_result_selected)
            
            generator_layout.addWidget(self.generation_results)
            
            basic_layout.addWidget(generator_group)
            
            # Initial UI state based on mode
            self._on_mode_changed()
        
        content_tabs.addTab(basic_tab, "Basic")
        
        # Advanced tab (only for existing items)
        if self.item:
            advanced_tab = QWidget()
            advanced_layout = QVBoxLayout(advanced_tab)
            
            # SR parameters
            sr_group = QGroupBox("Spaced Repetition Parameters")
            sr_layout = QFormLayout(sr_group)
            
            # Interval
            self.interval_spin = QSpinBox()
            self.interval_spin.setRange(0, 3650)
            self.interval_spin.setSuffix(" days")
            sr_layout.addRow("Interval:", self.interval_spin)
            
            # Repetitions
            self.repetitions_spin = QSpinBox()
            self.repetitions_spin.setRange(0, 1000)
            sr_layout.addRow("Repetitions:", self.repetitions_spin)
            
            # Easiness
            self.easiness_spin = QDoubleSpinBox()
            self.easiness_spin.setRange(1.3, 5.0)
            self.easiness_spin.setSingleStep(0.1)
            self.easiness_spin.setDecimals(1)
            sr_layout.addRow("Easiness:", self.easiness_spin)
            
            # Reset parameters checkbox
            self.reset_sr_check = QCheckBox("Reset SR parameters on save")
            sr_layout.addRow("", self.reset_sr_check)
            
            advanced_layout.addWidget(sr_group)
            
            # Review history
            history_group = QGroupBox("Review History")
            history_layout = QVBoxLayout(history_group)
            
            self.history_table = QTableWidget()
            self.history_table.setColumnCount(4)
            self.history_table.setHorizontalHeaderLabels(["Date", "Grade", "Response Time", "Interval"])
            self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            
            history_layout.addWidget(self.history_table)
            
            advanced_layout.addWidget(history_group)
            
            content_tabs.addTab(advanced_tab, "Advanced")
        
        main_layout.addWidget(content_tabs)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)
        
        # Generate more button (only for new items)
        if not self.item:
            self.generate_more_button = QPushButton("Generate More")
            self.generate_more_button.clicked.connect(self._on_generate_more)
            button_layout.addWidget(self.generate_more_button)
        
        button_layout.addStretch()
        
        # Delete button (only for existing items)
        if self.item:
            self.delete_button = QPushButton("Delete")
            self.delete_button.clicked.connect(self._on_delete)
            button_layout.addWidget(self.delete_button)
        
        main_layout.addLayout(button_layout)
    
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
        if self.qa_radio.isChecked():
            # Question-Answer mode
            self.question_edit.setPlaceholderText("Enter the question")
            self.answer_edit.setPlaceholderText("Enter the answer")
        else:
            # Cloze deletion mode
            self.question_edit.setPlaceholderText("Enter text with [...] for cloze deletion")
            self.answer_edit.setPlaceholderText("Enter the text that goes in place of [...]")
    
    @pyqtSlot()
    def _on_mode_changed(self):
        """Handle content generation mode change."""
        if hasattr(self, 'auto_mode_combo') and hasattr(self, 'provider_label') and hasattr(self, 'provider_combo'):
            # Show/hide provider selection based on mode
            use_ai = self.auto_mode_combo.currentData() == "ai"
            self.provider_label.setVisible(use_ai)
            self.provider_combo.setVisible(use_ai)
    
    @pyqtSlot()
    def _on_generate(self):
        """Generate content suggestions."""
        if not self.extract:
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
                    QMessageBox.warning(
                        self, "No API Key", 
                        "No API key set for the selected provider. Falling back to template-based generation."
                    )
                    items = self._generate_with_templates(count)
                else:
                    # AI-assisted generation with the configured provider
                    items = self._generate_with_ai(count, api_config)
            else:
                # AI-assisted generation with the configured provider
                items = self._generate_with_ai(count, api_config)
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
            api_key = settings.get_setting("ai", setting_key, "")
            
            # Get saved model for this provider or use default
            model_setting_key = f"{provider_id}_model"
            model = settings.get_setting("ai", model_setting_key, AI_PROVIDERS[provider_id]["default_model"])
            
            # If no API key, return empty config
            if not api_key:
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
            current_key = settings.get_setting("ai", setting_key, "")
            
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
                settings.set_setting("ai", setting_key, api_key)
                
                # Save default model
                from core.document_processor.summarizer import AI_PROVIDERS
                model = AI_PROVIDERS[provider_id]["default_model"]
                model_setting_key = f"{provider_id}_model"
                settings.set_setting("ai", model_setting_key, model)
                
                settings.save_settings()
                
                return True
            
        except Exception as e:
            logger.exception(f"Error setting API key: {e}")
        
        return False
    
    @pyqtSlot(QTableWidgetItem)
    def _on_result_selected(self, item):
        """Handle selection of a generated item."""
        if item.column() in [1, 2]:  # Question or answer column
            row = item.row()
            
            # Get question and answer
            question = self.generation_results.item(row, 1).text()
            answer = self.generation_results.item(row, 2).text()
            
            # Set in the editor
            self.question_edit.setText(question)
            self.answer_edit.setText(answer)
    
    @pyqtSlot()
    def _on_generate_more(self):
        """Handle generate more button."""
        # Check selected items
        selected_items = []
        
        for i in range(self.generation_results.rowCount()):
            use_check = self.generation_results.item(i, 0)
            
            if use_check and use_check.checkState() == Qt.CheckState.Checked:
                question = self.generation_results.item(i, 1).text()
                answer = self.generation_results.item(i, 2).text()
                
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
                item_type='qa' if self.qa_radio.isChecked() else 'cloze',
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
    
    @pyqtSlot()
    def _on_save(self):
        """Save the learning item."""
        # Validate content
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
        
        try:
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
                self.question_edit.clear()
                self.answer_edit.clear()
            
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
