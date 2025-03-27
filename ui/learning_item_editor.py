# ui/learning_item_editor.py

import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QTextEdit, QComboBox, QSpinBox,
    QGroupBox, QFormLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QMessageBox,
    QRadioButton, QButtonGroup, QCheckBox, QDoubleSpinBox,
    QPlainTextEdit, QAbstractItemView, QLineEdit, QDialogButtonBox,
    QInputDialog, QColorDialog, QApplication, QShortcut
)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QIcon, QColor, QFont, QPalette, QKeySequence
# Import sip from PyQt5 instead of standalone sip
from PyQt5 import sip

from core.knowledge_base.models import Extract, LearningItem, ReviewLog
from core.content_extractor.nlp_extractor import NLPExtractor
# Remove non-existent imports
# from ui.dialog_manager import DialogManager
# from core.models import LearningItemReview
# from core.spaced_repetition import SpacedRepetition

logger = logging.getLogger(__name__)

class LearningItemEditor(QDialog):
    """Dialog for editing learning items."""
    
    itemSaved = pyqtSignal(int)  # item_id
    itemDeleted = pyqtSignal(int)  # item_id
    
    def __init__(self, db_session, item_id=None, extract_id=None, settings_manager=None, theme_manager=None):
        super().__init__()
        
        self.db_session = db_session
        self.item_id = item_id
        self.extract_id = extract_id
        self.settings_manager = settings_manager
        self.theme_manager = theme_manager
        
        # Customization settings with defaults
        self.editor_font_size = 12
        self.editor_font_family = "Arial"
        self.editor_line_height = 1.2
        self.custom_highlight_color = "#FFFF99"  # Light yellow
        
        # Load editor settings
        self._load_editor_settings()
        
        self.item = None
        self.extract = None
        self.nlp_extractor = NLPExtractor(db_session)
        
        # Cached content to avoid accessing destroyed widgets
        self._cached_question = None
        self._cached_answer = None
        self._cached_priority = 3  # Default priority
        self._cached_is_qa = True  # Default item type
        
        # Flags to track widget state
        self._is_closing = False
        self._is_saving = False
        
        # Load data
        self._load_data()
        
        # Set up UI
        self._create_ui()
        
        # Apply current theme
        self._apply_theme()
        
        # Set up signal-slot connections for content caching
        if hasattr(self, 'question_edit'):
            self.question_edit.textChanged.connect(self._on_question_changed)
        if hasattr(self, 'answer_edit'):
            self.answer_edit.textChanged.connect(self._on_answer_changed)
        if hasattr(self, 'priority_spin'):
            self.priority_spin.valueChanged.connect(self._on_priority_changed)
            
        # Load item content if editing existing item
        if self.item:
            self._load_item_data()
            
        # Set window properties
        self.setWindowTitle("Learning Item Editor")
        self.resize(900, 700)  # Slightly larger default size
    
    def _load_editor_settings(self):
        """Load editor customization settings."""
        if not self.settings_manager:
            logger.warning("Settings manager not available, using default editor settings")
            return
            
        try:
            # Font settings
            self.editor_font_family = self.settings_manager.get_setting("editor", "font_family", "Arial")
            self.editor_font_size = self.settings_manager.get_setting("editor", "font_size", 12)
            self.editor_line_height = self.settings_manager.get_setting("editor", "line_height", 1.2)
            
            # Color settings
            self.custom_highlight_color = self.settings_manager.get_setting("editor", "highlight_color", "#FFFF99")
            
            logger.debug(f"Loaded editor settings: font={self.editor_font_family}, size={self.editor_font_size}")
        except Exception as e:
            logger.warning(f"Error loading editor settings: {e}")
    
    def _apply_theme(self):
        """Apply the current theme to the editor."""
        if not self.theme_manager:
            logger.debug("Theme manager not available, skipping theme application")
            return
            
        try:
            # Apply global theme stylesheet
            theme_stylesheet = self.theme_manager.get_current_stylesheet()
            if theme_stylesheet:
                self.setStyleSheet(theme_stylesheet)
                
            # Get theme colors for editor customization
            theme_colors = self.theme_manager.get_current_colors()
            
            # Apply theme colors to specific elements
            if hasattr(self, 'question_edit') and not sip.isdeleted(self.question_edit):
                self._style_text_editor(self.question_edit, theme_colors)
                
            if hasattr(self, 'answer_edit') and not sip.isdeleted(self.answer_edit):
                self._style_text_editor(self.answer_edit, theme_colors)
                
            # Style the generation results table
            if hasattr(self, 'generation_results') and not sip.isdeleted(self.generation_results):
                self._style_table(self.generation_results, theme_colors)
                
            logger.debug(f"Applied theme to learning item editor")
        except Exception as e:
            logger.warning(f"Error applying theme: {e}")
    
    def _style_text_editor(self, editor, theme_colors=None):
        """Apply custom styling to a text editor."""
        try:
            # Set font
            font = editor.font()
            font.setFamily(self.editor_font_family)
            font.setPointSize(self.editor_font_size)
            editor.setFont(font)
            
            # Set colors if theme is provided
            if theme_colors:
                # Create a stylesheet for the editor
                editor_style = f"""
                QTextEdit {{
                    background-color: {theme_colors.get('background', '#FFFFFF')};
                    color: {theme_colors.get('text', '#000000')};
                    border: 1px solid {theme_colors.get('border', '#CCCCCC')};
                    border-radius: 4px;
                    padding: 6px;
                    selection-background-color: {theme_colors.get('selection', '#5294e2')};
                }}
                """
                editor.setStyleSheet(editor_style)
        except Exception as e:
            logger.warning(f"Error styling text editor: {e}")
    
    def _style_table(self, table, theme_colors=None):
        """Apply custom styling to a table widget."""
        try:
            if theme_colors:
                # Create a stylesheet for the table
                table_style = f"""
                QTableWidget {{
                    background-color: {theme_colors.get('background', '#FFFFFF')};
                    color: {theme_colors.get('text', '#000000')};
                    border: 1px solid {theme_colors.get('border', '#CCCCCC')};
                    border-radius: 4px;
                    gridline-color: {theme_colors.get('divider', '#DDDDDD')};
                }}
                QTableWidget::item:selected {{
                    background-color: {theme_colors.get('selection', '#5294e2')};
                    color: {theme_colors.get('selected_text', '#FFFFFF')};
                }}
                QHeaderView::section {{
                    background-color: {theme_colors.get('header', '#E0E0E0')};
                    color: {theme_colors.get('text', '#000000')};
                    padding: 4px;
                    border: 1px solid {theme_colors.get('border', '#CCCCCC')};
                }}
                """
                table.setStyleSheet(table_style)
                
                # Set alternate row colors for better readability
                table.setAlternatingRowColors(True)
        except Exception as e:
            logger.warning(f"Error styling table: {e}")
    
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
    
    def _load_item_data(self):
        """Load item data into the UI if editing an existing item."""
        if not self.item:
            return
            
        # Set item data - but also immediately cache the values
        if hasattr(self, 'question_edit') and not sip.isdeleted(self.question_edit):
            self.question_edit.setText(self.item.question)
            self._cached_question = self.item.question
            
        if hasattr(self, 'answer_edit') and not sip.isdeleted(self.answer_edit):
            self.answer_edit.setText(self.item.answer)
            self._cached_answer = self.item.answer
            
        if hasattr(self, 'priority_spin') and not sip.isdeleted(self.priority_spin):
            self.priority_spin.setValue(self.item.priority)
            self._cached_priority = self.item.priority
            
        # Set item type
        if self.item.item_type == 'qa':
            self._cached_is_qa = True
            if hasattr(self, 'qa_radio') and not sip.isdeleted(self.qa_radio):
                self.qa_radio.setChecked(True)
        else:
            self._cached_is_qa = False
            if hasattr(self, 'cloze_radio') and not sip.isdeleted(self.cloze_radio):
                self.cloze_radio.setChecked(True)
                
        logger.debug(f"Loaded item data: Q({len(self._cached_question) if self._cached_question else 0} chars), "
                    f"A({len(self._cached_answer) if self._cached_answer else 0} chars), "
                    f"P({self._cached_priority})")
    
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
        """Handle item type change."""
        if not hasattr(self, 'qa_radio') or not hasattr(self, 'cloze_radio'):
            return
            
        if self._is_closing:
            return
            
        try:
            # Cache the type selection 
            self._cached_is_qa = self.qa_radio.isChecked() if not sip.isdeleted(self.qa_radio) else self._cached_is_qa
            
            # Update labels based on type
            is_qa = self._cached_is_qa
            
            if hasattr(self, 'question_edit') and not sip.isdeleted(self.question_edit):
                question_label = self.question_edit.parentWidget().layout().labelForField(self.question_edit)
                if question_label and not sip.isdeleted(question_label):
                    question_label.setText("Question:" if is_qa else "Cloze Text:")
                    
            if hasattr(self, 'answer_edit') and not sip.isdeleted(self.answer_edit):
                answer_label = self.answer_edit.parentWidget().layout().labelForField(self.answer_edit)
                if answer_label and not sip.isdeleted(answer_label):
                    answer_label.setText("Answer:" if is_qa else "Full Text:")
                    
        except Exception as e:
            logger.warning(f"Error updating type labels: {e}")
            
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
        # Get selected item type
        item_type = self.item_type_combo.currentData()
        
        if not self.extract:
            logger.error("No extract available for AI generation")
            return []
            
        try:
            # For mixed items, distribute the count among different item types
            if item_type == "mixed":
                # Create a variety of item types
                items = []
                types = ["qa", "cloze", "analogy", "concept"]
                
                # Calculate how many of each type to generate
                per_type = max(1, count // len(types))
                remaining = count
                
                for t in types:
                    if remaining <= 0:
                        break
                    count_for_type = min(per_type, remaining)
                    remaining -= count_for_type
                    
                    items.extend(self._generate_specific_ai_items(t, count_for_type, api_config))
                    
                return items
            else:
                # Generate specific type
                return self._generate_specific_ai_items(item_type, count, api_config)
                
        except Exception as e:
            logger.exception(f"Error in AI generation: {e}")
            # Fall back to template generation
            if self.qa_radio.isChecked():
                return self._generate_template_qa(count)
            else:
                return self._generate_template_cloze(count)
    
    def _generate_specific_ai_items(self, item_type, count, api_config):
        """Generate specific type of learning items using AI."""
        if item_type == "qa":
            return self.nlp_extractor.generate_qa_pairs(self.extract_id, max_pairs=count, ai_config=api_config)
        elif item_type == "cloze":
            return self.nlp_extractor.generate_cloze_deletions(self.extract_id, max_items=count, ai_config=api_config)
        elif item_type == "analogy":
            # Generate analogies using AI
            return self._generate_ai_analogies(count, api_config)
        elif item_type == "concept":
            # Generate concept definitions using AI
            return self._generate_ai_concepts(count, api_config)
        else:
            # Default to QA pairs if type is unknown
            return self.nlp_extractor.generate_qa_pairs(self.extract_id, max_pairs=count, ai_config=api_config)
    
    def _generate_ai_analogies(self, count, api_config):
        """Generate analogy-based learning items using AI."""
        from datetime import datetime
        
        if not self.extract:
            return []
            
        provider = api_config.get('provider', 'openai')
        api_key = api_config.get('api_key')
        model = api_config.get('model')
        
        if not api_key:
            raise ValueError("No API key provided")
            
        # Create a prompt for generating analogies
        prompt = f"""
        Create {count} analogy-based learning items from the following text. 
        Each analogy should help understand a concept by comparing it to something familiar.
        Format each as a question and answer pair where:
        - The question asks for an analogy that explains a concept
        - The answer provides a clear, intuitive analogy
        
        TEXT:
        {self.extract.content}
        
        OUTPUT FORMAT:
        - Question: [Question]
        - Answer: [Answer]
        """
        
        # Generate the analogies using appropriate API
        try:
            from core.document_processor.summarizer import DocumentSummarizer
            summarizer = DocumentSummarizer(self.db_session, api_config=api_config)
            if provider == 'openai':
                response = summarizer._openai_summarize(prompt, "", api_key, model, 2000)
            elif provider == 'anthropic':
                response = summarizer._anthropic_summarize(prompt, "", api_key, model, 2000)
            elif provider == 'openrouter':
                response = summarizer._openrouter_summarize(prompt, "", api_key, model, 2000)
            elif provider == 'google':
                response = summarizer._google_summarize(prompt, "", api_key, model, 2000)
            else:
                raise ValueError(f"Unsupported provider: {provider}")
                
            # Parse the response to extract question-answer pairs
            items = []
            current_question = None
            current_answer = None
            
            for line in response.strip().split('\n'):
                line = line.strip()
                if line.startswith('- Question:') or line.startswith('Question:'):
                    # Save previous item if exists
                    if current_question and current_answer:
                        item = LearningItem(
                            extract_id=self.extract_id,
                            item_type='qa',
                            question=current_question,
                            answer=current_answer,
                            priority=self.extract.priority,
                            created_date=datetime.utcnow()
                        )
                        self.db_session.add(item)
                        items.append(item)
                    
                    # Start new item
                    current_question = line.split(':', 1)[1].strip()
                    current_answer = None
                elif line.startswith('- Answer:') or line.startswith('Answer:'):
                    current_answer = line.split(':', 1)[1].strip()
            
            # Add the last item
            if current_question and current_answer:
                item = LearningItem(
                    extract_id=self.extract_id,
                    item_type='qa',
                    question=current_question,
                    answer=current_answer,
                    priority=self.extract.priority,
                    created_date=datetime.utcnow()
                )
                self.db_session.add(item)
                items.append(item)
                
            self.db_session.commit()
            return items
            
        except Exception as e:
            logger.exception(f"Error generating analogies: {e}")
            return []
    
    def _generate_ai_concepts(self, count, api_config):
        """Generate concept definition learning items using AI."""
        from datetime import datetime
        
        if not self.extract:
            return []
            
        provider = api_config.get('provider', 'openai')
        api_key = api_config.get('api_key')
        model = api_config.get('model')
        
        if not api_key:
            raise ValueError("No API key provided")
            
        # Create a prompt for generating concept definitions
        prompt = f"""
        Extract {count} key concepts from the following text and create learning items.
        For each concept:
        - The question should ask for a definition or explanation of the concept
        - The answer should provide a clear, concise definition
        
        TEXT:
        {self.extract.content}
        
        OUTPUT FORMAT:
        - Question: What is [concept]? OR How does [concept] work? OR Define [concept].
        - Answer: [Clear, concise definition or explanation]
        """
        
        # Generate the concepts using appropriate API
        try:
            from core.document_processor.summarizer import DocumentSummarizer
            summarizer = DocumentSummarizer(self.db_session, api_config=api_config)
            if provider == 'openai':
                response = summarizer._openai_summarize(prompt, "", api_key, model, 2000)
            elif provider == 'anthropic':
                response = summarizer._anthropic_summarize(prompt, "", api_key, model, 2000)
            elif provider == 'openrouter':
                response = summarizer._openrouter_summarize(prompt, "", api_key, model, 2000)
            elif provider == 'google':
                response = summarizer._google_summarize(prompt, "", api_key, model, 2000)
            else:
                raise ValueError(f"Unsupported provider: {provider}")
                
            # Parse the response to extract question-answer pairs
            items = []
            current_question = None
            current_answer = None
            
            for line in response.strip().split('\n'):
                line = line.strip()
                if line.startswith('- Question:') or line.startswith('Question:'):
                    # Save previous item if exists
                    if current_question and current_answer:
                        item = LearningItem(
                            extract_id=self.extract_id,
                            item_type='qa',
                            question=current_question,
                            answer=current_answer,
                            priority=self.extract.priority,
                            created_date=datetime.utcnow()
                        )
                        self.db_session.add(item)
                        items.append(item)
                    
                    # Start new item
                    current_question = line.split(':', 1)[1].strip()
                    current_answer = None
                elif line.startswith('- Answer:') or line.startswith('Answer:'):
                    current_answer = line.split(':', 1)[1].strip()
            
            # Add the last item
            if current_question and current_answer:
                item = LearningItem(
                    extract_id=self.extract_id,
                    item_type='qa',
                    question=current_question,
                    answer=current_answer,
                    priority=self.extract.priority,
                    created_date=datetime.utcnow()
                )
                self.db_session.add(item)
                items.append(item)
                
            self.db_session.commit()
            return items
            
        except Exception as e:
            logger.exception(f"Error generating concept definitions: {e}")
            return []
    
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
            
            from PyQt5.QtWidgets import QInputDialog, QLineEdit
            
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
                
    def _on_save(self):
        """Save the current learning item."""
        if self._is_closing or self._is_saving:
            logger.warning("Save operation interrupted - widget is closing or another save in progress")
            return
            
        # Set flag to indicate we're in the process of saving
        self._is_saving = True
        
        try:
            # Cache all content first to ensure we have the latest values
            self._cache_all_content()
            
            # Validate required fields from cached content
            if not self._cached_question or not self._cached_question.strip():
                QMessageBox.warning(self, "Missing Field", "Please enter a question.")
                self._is_saving = False
                return
                
            if not self._cached_answer or not self._cached_answer.strip():
                QMessageBox.warning(self, "Missing Field", "Please enter an answer.")
                self._is_saving = False
                return
            
            # Start a transaction
            with self.db_session.begin_nested():
                if self.item:  # Update existing item
                    logger.debug(f"Updating item {self.item.id}")
                    
                    # Update fields from cached values
                    self.item.question = self._cached_question
                    self.item.answer = self._cached_answer
                    self.item.priority = self._cached_priority
                    
                    # Reset spaced repetition parameters if question or answer changed
                    if (self.item.question != self._cached_question or 
                        self.item.answer != self._cached_answer):
                        self.item.reset_spaced_repetition()
                        
                    # Commit the changes
                    self.db_session.commit()
                    
                    # Show success message
                    QMessageBox.information(self, "Success", "Learning item updated successfully.")
                    
                    # Emit signal
                    self.itemSaved.emit(self.item.id)
                    
                else:  # Create new item
                    logger.debug("Creating new learning item")
                    
                    # Create item from cached values
                    item = LearningItem(
                        extract_id=self.extract_id,
                        item_type='qa' if self._cached_is_qa else 'cloze',
                        question=self._cached_question,
                        answer=self._cached_answer,
                        priority=self._cached_priority,
                        created_date=datetime.utcnow()
                    )
                    
                    # Add to database
                    self.db_session.add(item)
                    self.db_session.commit()
                    
                    # Update item ID so we're now in edit mode
                    self.item = item
                    self.item_id = item.id
                    
                    # Mark extract as processed
                    if self.extract:
                        self.extract.processed = True
                        self.db_session.commit()
                    
                    # Show success message
                    QMessageBox.information(self, "Success", "Learning item created successfully.")
                    
                    # Emit signal
                    self.itemSaved.emit(item.id)
                    
                    # Clear cached content for new items
                    self._cached_question = None
                    self._cached_answer = None
                    
            # Close the dialog after save
            self.close()
            
        except Exception as e:
            # Handle any errors
            logger.error(f"Error saving learning item: {e}")
            QMessageBox.critical(self, "Error", f"An error occurred while saving: {str(e)}")
            self.db_session.rollback()
        
        finally:
            # Reset saving flag
            self._is_saving = False
    
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
            
    def _on_question_changed(self):
        """Cache question content when it changes."""
        if not self._is_closing and hasattr(self, 'question_edit') and not sip.isdeleted(self.question_edit):
            self._cached_question = self.question_edit.toPlainText()
            
    def _on_answer_changed(self):
        """Cache answer content when it changes."""
        if not self._is_closing and hasattr(self, 'answer_edit') and not sip.isdeleted(self.answer_edit):
            self._cached_answer = self.answer_edit.toPlainText()
            
    def _on_priority_changed(self, value):
        """Cache priority value when it changes."""
        if not self._is_closing:
            self._cached_priority = value
    
    def closeEvent(self, event):
        """Handle widget close event."""
        # Set closing flag first to prevent further widget access
        self._is_closing = True
        
        # Cache content before disconnecting signals
        if not self._is_saving:
            try:
                self._cache_all_content()
            except Exception as e:
                logger.warning(f"Error caching content during close: {e}")
        
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
            
            # Disconnect content caching signals
            if hasattr(self, 'question_edit') and not sip.isdeleted(self.question_edit):
                self._safe_disconnect(self.question_edit, 'textChanged')
            if hasattr(self, 'answer_edit') and not sip.isdeleted(self.answer_edit):
                self._safe_disconnect(self.answer_edit, 'textChanged')
            if hasattr(self, 'priority_spin') and not sip.isdeleted(self.priority_spin):
                self._safe_disconnect(self.priority_spin, 'valueChanged')
                    
        except Exception as e:
            logger.warning(f"Error disconnecting signals: {e}")
            
        # Auto-save if we have cached content that hasn't been saved
        if not self.item and self._cached_question and self._cached_answer and not self._is_saving:
            try:
                # Save the item directly without accessing widgets
                item = LearningItem(
                    extract_id=self.extract_id,
                    item_type='qa' if self._cached_is_qa else 'cloze',
                    question=self._cached_question,
                    answer=self._cached_answer,
                    priority=self._cached_priority,
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
                logger.info(f"Auto-saved learning item on close: {item.id}")
            except Exception as e:
                logger.warning(f"Error auto-saving on close: {e}")
        
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

    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)  # More spacing between elements
        main_layout.setContentsMargins(15, 15, 15, 15)  # Add more padding around the edges
        
        # Header with better styling
        if self.item:
            title = "Edit Learning Item"
        else:
            title = "Create Learning Item"
        
        header_label = QLabel(f"<h1 style='color: #3E7BFA;'>{title}</h1>")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # Center the header
        main_layout.addWidget(header_label)
        
        # Extract preview (if available)
        if self.extract:
            extract_group = QGroupBox("Source Extract")
            extract_group.setStyleSheet("QGroupBox { font-weight: bold; }")
            extract_layout = QVBoxLayout(extract_group)
            extract_layout.setContentsMargins(10, 15, 10, 10)
            
            extract_text = QTextEdit()
            extract_text.setReadOnly(True)
            extract_text.setText(self.extract.content)
            extract_text.setMaximumHeight(150)
            
            # Apply text styling to extract preview
            if self.theme_manager:
                theme_colors = self.theme_manager.get_current_colors()
                self._style_text_editor(extract_text, theme_colors)
            
            extract_layout.addWidget(extract_text)
            
            main_layout.addWidget(extract_group)
        
        # Content tab widget with better styling
        content_tabs = QTabWidget()
        content_tabs.setDocumentMode(True)  # More modern look
        content_tabs.setStyleSheet("""
            QTabWidget::pane { 
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #3E7BFA;
                color: white;
            }
        """)
        
        # ========== Basic Editor Tab ==========
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setContentsMargins(12, 12, 12, 12)
        basic_layout.setSpacing(15)
        
        # Item type selection with better styling
        type_group = QGroupBox("Item Type")
        type_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        type_layout = QHBoxLayout(type_group)
        type_layout.setContentsMargins(15, 20, 15, 15)
        
        self.type_group = QButtonGroup(self)
        
        self.qa_radio = QRadioButton("Question-Answer")
        self.qa_radio.setChecked(True)
        self.qa_radio.setStyleSheet("QRadioButton { font-size: 14px; }")
        self.type_group.addButton(self.qa_radio)
        type_layout.addWidget(self.qa_radio)
        
        self.cloze_radio = QRadioButton("Cloze Deletion")
        self.cloze_radio.setStyleSheet("QRadioButton { font-size: 14px; }")
        self.type_group.addButton(self.cloze_radio)
        type_layout.addWidget(self.cloze_radio)
        
        # Connect signals
        self.qa_radio.toggled.connect(self._on_type_changed)
        self.cloze_radio.toggled.connect(self._on_type_changed)
        
        basic_layout.addWidget(type_group)
        
        # Item content form
        content_group = QGroupBox("Item Content")
        content_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        form_layout = QFormLayout(content_group)
        form_layout.setSpacing(15)  # More spacing in the form
        form_layout.setContentsMargins(15, 20, 15, 15)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Question
        question_label = QLabel("Question:")
        question_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.question_edit = QTextEdit()
        # Set minimum height for better usability
        self.question_edit.setMinimumHeight(120)
        # Add placeholder text
        self.question_edit.setPlaceholderText("Enter your question here...")
        form_layout.addRow(question_label, self.question_edit)
        
        # Answer
        answer_label = QLabel("Answer:")
        answer_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.answer_edit = QTextEdit()
        self.answer_edit.setMinimumHeight(170)  # Taller for answer
        self.answer_edit.setPlaceholderText("Enter your answer here...")
        form_layout.addRow(answer_label, self.answer_edit)
        
        # Editor toolbar for formatting - more modern look with icons
        format_layout = QHBoxLayout()
        format_layout.setSpacing(8)
        
        # Get icon path - try common locations
        icon_paths = [
            os.path.join(os.path.dirname(__file__), "icons"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons"),
            "/usr/share/icons/hicolor/16x16/actions",
        ]
        
        def get_icon(name):
            """Try to find an icon in common paths."""
            for path in icon_paths:
                icon_file = os.path.join(path, f"{name}.png")
                if os.path.exists(icon_file):
                    return QIcon(icon_file)
            # Fallback to theme icon
            return QIcon.fromTheme(name, QIcon())
        
        # Bold button
        bold_btn = QPushButton()
        bold_btn.setToolTip("Make selected text bold (Ctrl+B)")
        bold_btn.setIcon(get_icon("format-text-bold"))
        bold_btn.setFixedSize(32, 32)
        bold_btn.clicked.connect(lambda: self._format_text('<b>', '</b>'))
        
        # Italic button
        italic_btn = QPushButton()
        italic_btn.setToolTip("Make selected text italic (Ctrl+I)")
        italic_btn.setIcon(get_icon("format-text-italic"))
        italic_btn.setFixedSize(32, 32)
        italic_btn.clicked.connect(lambda: self._format_text('<i>', '</i>'))
        
        # Highlight button
        highlight_btn = QPushButton()
        highlight_btn.setToolTip("Highlight selected text")
        highlight_btn.setIcon(get_icon("format-text-highlight"))
        highlight_btn.setFixedSize(32, 32)
        highlight_btn.clicked.connect(lambda: self._format_text(
            f'<span style="background-color:{self.custom_highlight_color}">', 
            '</span>'
        ))
        
        # Code button
        code_btn = QPushButton()
        code_btn.setToolTip("Format selected text as code")
        code_btn.setIcon(get_icon("format-text-code"))
        code_btn.setFixedSize(32, 32)
        code_btn.clicked.connect(lambda: self._format_text('<code>', '</code>'))
        
        # Clear formatting button
        clear_btn = QPushButton()
        clear_btn.setToolTip("Remove formatting from selected text")
        clear_btn.setIcon(get_icon("format-text-clear"))
        clear_btn.setFixedSize(32, 32)
        clear_btn.clicked.connect(self._clear_formatting)
        
        # Create button style
        button_style = """
        QPushButton {
            border: 1px solid #cccccc;
            border-radius: 4px;
            padding: 4px;
            background-color: #f5f5f5;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        QPushButton:pressed {
            background-color: #d0d0d0;
        }
        """
        
        # Apply style to all buttons
        for btn in [bold_btn, italic_btn, highlight_btn, code_btn, clear_btn]:
            btn.setStyleSheet(button_style)
        
        format_layout.addWidget(bold_btn)
        format_layout.addWidget(italic_btn)
        format_layout.addWidget(highlight_btn)
        format_layout.addWidget(code_btn)
        format_layout.addWidget(clear_btn)
        format_layout.addStretch()
        
        form_layout.addRow("Formatting:", format_layout)
        
        # Priority with slider and labels
        priority_layout = QHBoxLayout()
        priority_layout.setSpacing(10)
        
        # Add priority labels with styling
        priority_low = QLabel("Low Priority")
        priority_low.setStyleSheet("color: #888888;")
        
        # Use a more visual priority selector
        self.priority_spin = QSpinBox()
        self.priority_spin.setRange(1, 5)
        self.priority_spin.setValue(3)
        self.priority_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                min-height: 24px;
            }
        """)
        
        priority_high = QLabel("High Priority")
        priority_high.setStyleSheet("color: #FF5555;")
        
        priority_layout.addWidget(priority_low)
        priority_layout.addWidget(self.priority_spin)
        priority_layout.addWidget(priority_high)
        priority_layout.addStretch()
        
        form_layout.addRow("Priority:", priority_layout)
        
        basic_layout.addWidget(content_group)
        
        # ========== Add keyboard shortcuts for formatting ==========
        # These will work when focus is in text editors
        from PyQt5.QtGui import QShortcut, QKeySequence
        
        # Bold shortcut (Ctrl+B)
        bold_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        bold_shortcut.activated.connect(lambda: self._format_text('<b>', '</b>'))
        
        # Italic shortcut (Ctrl+I)
        italic_shortcut = QShortcut(QKeySequence("Ctrl+I"), self)
        italic_shortcut.activated.connect(lambda: self._format_text('<i>', '</i>'))
        
        # Highlight shortcut (Ctrl+H)
        highlight_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        highlight_shortcut.activated.connect(lambda: self._format_text(
            f'<span style="background-color:{self.custom_highlight_color}">', 
            '</span>'
        ))
        
        # Code shortcut (Ctrl+K)
        code_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        code_shortcut.activated.connect(lambda: self._format_text('<code>', '</code>'))
        
        # ========== Generation Tab ==========
        generation_tab = QWidget()
        generation_layout = QVBoxLayout(generation_tab)
        generation_layout.setContentsMargins(12, 12, 12, 12)
        generation_layout.setSpacing(15)
        
        # Generation options
        options_group = QGroupBox("Generation Options")
        options_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        options_layout = QFormLayout(options_group)
        options_layout.setContentsMargins(15, 20, 15, 15)
        options_layout.setSpacing(12)
        
        # Generation mode
        self.auto_mode_combo = QComboBox()
        self.auto_mode_combo.addItem("Template-based", "template")
        self.auto_mode_combo.addItem("AI-assisted", "ai")
        self.auto_mode_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                min-height: 24px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid #cccccc;
            }
        """)
        options_layout.addRow("Generation Mode:", self.auto_mode_combo)
        
        # Provider selection (only visible in AI mode)
        self.provider_container = QWidget()
        provider_layout = QHBoxLayout(self.provider_container)
        provider_layout.setContentsMargins(0, 0, 0, 0)
        
        self.provider_combo = QComboBox()
        self.provider_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                min-height: 24px;
            }
        """)
        
        # Add settings button
        self.api_settings_btn = QPushButton("⚙️")
        self.api_settings_btn.setToolTip("Open API settings")
        self.api_settings_btn.setMaximumWidth(30)
        self.api_settings_btn.setStyleSheet(button_style)
        
        provider_layout.addWidget(self.provider_combo)
        provider_layout.addWidget(self.api_settings_btn)
        options_layout.addRow("AI Provider:", self.provider_container)
        
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
        
        # Item type selection
        self.item_type_combo = QComboBox()
        self.item_type_combo.addItem("Mixed (Variety)", "mixed")
        self.item_type_combo.addItem("Question-Answer", "qa")
        self.item_type_combo.addItem("Cloze Deletion", "cloze")
        self.item_type_combo.addItem("Analogy", "analogy")
        self.item_type_combo.addItem("Concept Definition", "concept")
        self.item_type_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                min-height: 24px;
            }
        """)
        options_layout.addRow("Item Types:", self.item_type_combo)
        
        # Count selection
        self.question_count = QSpinBox()
        self.question_count.setRange(1, 20)
        self.question_count.setValue(5)
        self.question_count.setStyleSheet("""
            QSpinBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                min-height: 24px;
            }
        """)
        options_layout.addRow("Number of items:", self.question_count)
        
        generation_layout.addWidget(options_group)
        
        # Generate button with better styling
        generate_layout = QHBoxLayout()
        generate_layout.addStretch()
        self.generate_btn = QPushButton("Generate Items")
        self.generate_btn.setMinimumHeight(40)  # Taller button for emphasis
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #3E7BFA;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2E6BEA;
            }
            QPushButton:pressed {
                background-color: #1E5BDA;
            }
        """)
        generate_layout.addWidget(self.generate_btn)
        generation_layout.addLayout(generate_layout)
        
        # Results group
        results_group = QGroupBox("Generated Items")
        results_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        results_layout = QVBoxLayout(results_group)
        results_layout.setContentsMargins(15, 20, 15, 15)
        
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
        self.generation_results.setStyleSheet("""
            QTableWidget {
                border: 1px solid #cccccc;
                border-radius: 4px;
                gridline-color: #e0e0e0;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 6px;
                border: 1px solid #cccccc;
            }
        """)
        results_layout.addWidget(self.generation_results)
        
        # Add selected button
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        self.add_selected_btn = QPushButton("Add Selected Items")
        self.add_selected_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3C9F40;
            }
            QPushButton:pressed {
                background-color: #2C8F30;
            }
        """)
        action_layout.addWidget(self.add_selected_btn)
        results_layout.addLayout(action_layout)
        
        generation_layout.addWidget(results_group)
        
        # ========== Settings Tab ==========
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.setContentsMargins(12, 12, 12, 12)
        settings_layout.setSpacing(15)
        
        # Editor settings group
        editor_group = QGroupBox("Editor Settings")
        editor_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        editor_form = QFormLayout(editor_group)
        editor_form.setContentsMargins(15, 20, 15, 15)
        editor_form.setSpacing(12)
        
        # Font family
        self.font_family_combo = QComboBox()
        # Add common monospace and sans-serif fonts
        common_fonts = ["Arial", "Helvetica", "Verdana", "Tahoma", "Segoe UI", 
                      "Courier New", "Consolas", "Menlo", "Monaco"]
        self.font_family_combo.addItems(common_fonts)
        # Set current font
        current_index = self.font_family_combo.findText(self.editor_font_family)
        if current_index >= 0:
            self.font_family_combo.setCurrentIndex(current_index)
        self.font_family_combo.currentTextChanged.connect(self._on_font_changed)
        self.font_family_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                min-height: 24px;
            }
        """)
        editor_form.addRow("Font Family:", self.font_family_combo)
        
        # Font size
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(self.editor_font_size)
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        self.font_size_spin.setStyleSheet("""
            QSpinBox {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
                min-height: 24px;
            }
        """)
        editor_form.addRow("Font Size:", self.font_size_spin)
        
        # Highlight color
        self.highlight_color_btn = QPushButton()
        self.highlight_color_btn.setStyleSheet(
            f"background-color: {self.custom_highlight_color}; min-width: 60px; min-height: 24px; border: 1px solid #cccccc; border-radius: 4px;"
        )
        self.highlight_color_btn.clicked.connect(self._on_highlight_color)
        editor_form.addRow("Highlight Color:", self.highlight_color_btn)
        
        # Save settings button
        self.save_settings_btn = QPushButton("Save Editor Settings")
        self.save_settings_btn.clicked.connect(self._on_save_editor_settings)
        self.save_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #3E7BFA;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2E6BEA;
            }
            QPushButton:pressed {
                background-color: #1E5BDA;
            }
        """)
        
        settings_layout.addWidget(editor_group)
        settings_layout.addWidget(self.save_settings_btn)
        settings_layout.addStretch()
        
        # ========== History Tab (only for existing items) ==========
        if self.item_id:
            history_tab = QWidget()
            history_layout = QVBoxLayout(history_tab)
            history_layout.setContentsMargins(12, 12, 12, 12)
            
            # Create history table
            self.history_table = QTableWidget()
            self.history_table.setColumnCount(4)
            self.history_table.setHorizontalHeaderLabels(["Date", "Grade", "Response Time", "Interval"])
            self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.history_table.setStyleSheet("""
                QTableWidget {
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    gridline-color: #e0e0e0;
                }
                QHeaderView::section {
                    background-color: #f0f0f0;
                    padding: 6px;
                    border: 1px solid #cccccc;
                }
            """)
            
            history_layout.addWidget(self.history_table)
            
            # Load history data
            self._load_review_history()
            
            # Add to tabs
            content_tabs.addTab(history_tab, "Review History")
        
        # ========== Add all tabs ==========
        content_tabs.addTab(basic_tab, "Editor")
        content_tabs.addTab(generation_tab, "Generate")
        content_tabs.addTab(settings_tab, "Settings")
        
        main_layout.addWidget(content_tabs)
        
        # Button row
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()
        
        # Save and delete buttons
        if self.item_id:
            # Edit mode
            self.save_btn = QPushButton("Save Changes")
            self.delete_btn = QPushButton("Delete Item")
            self.save_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3E7BFA;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 10px 20px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #2E6BEA;
                }
                QPushButton:pressed {
                    background-color: #1E5BDA;
                }
            """)
            
            self.delete_btn = QPushButton("Delete Item")
            self.delete_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 10px 20px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #d62c1a;
                }
                QPushButton:pressed {
                    background-color: #c0392b;
                }
            """)
            
            button_layout.addWidget(self.save_btn)
            button_layout.addWidget(self.delete_btn)
        else:
            # Create mode
            self.save_btn = QPushButton("Create Item")
            self.save_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3E7BFA;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 10px 20px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #2E6BEA;
                }
                QPushButton:pressed {
                    background-color: #1E5BDA;
                }
            """)
            button_layout.addWidget(self.save_btn)
        
        main_layout.addLayout(button_layout)
        
        # Connect signals
        self.auto_mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self.generate_btn.clicked.connect(self._on_generate)
        self.add_selected_btn.clicked.connect(self._on_generate_more)
        self.save_btn.clicked.connect(self._on_save)
        self.generation_results.itemClicked.connect(self._on_result_selected)
        self.api_settings_btn.clicked.connect(self._on_open_api_settings)
        
        if self.item_id:
            self.delete_btn.clicked.connect(self._on_delete)
        
        # Initial UI state
        self._on_type_changed()
        self._on_mode_changed()
        
    def _format_text(self, prefix, suffix):
        """Apply HTML formatting to selected text in the active editor."""
        try:
            # Get the currently focused widget
            focused_widget = QApplication.focusWidget()
            
            # Only proceed if it's one of our text editors
            if focused_widget in [self.question_edit, self.answer_edit]:
                editor = focused_widget
                
                # Get selected text
                cursor = editor.textCursor()
                selected_text = cursor.selectedText()
                
                if selected_text:
                    # Apply formatting
                    formatted_text = f"{prefix}{selected_text}{suffix}"
                    cursor.insertHtml(formatted_text)
                    editor.setTextCursor(cursor)
        except Exception as e:
            logger.warning(f"Error applying text formatting: {e}")
    
    def _clear_formatting(self):
        """Remove HTML formatting from selected text in the active editor."""
        try:
            # Get the currently focused widget
            focused_widget = QApplication.focusWidget()
            
            # Only proceed if it's one of our text editors
            if focused_widget in [self.question_edit, self.answer_edit]:
                editor = focused_widget
                
                # Get selected text
                cursor = editor.textCursor()
                selected_text = cursor.selectedText()
                
                if selected_text:
                    # Strip HTML tags (simple approach)
                    import re
                    plain_text = re.sub(r'<[^>]*>', '', selected_text)
                    
                    # Replace with plain text
                    cursor.insertText(plain_text)
                    editor.setTextCursor(cursor)
        except Exception as e:
            logger.warning(f"Error clearing text formatting: {e}")
    
    def _on_font_changed(self, font_family):
        """Handle font family change."""
        try:
            self.editor_font_family = font_family
            
            # Update font in editors
            if hasattr(self, 'question_edit') and not sip.isdeleted(self.question_edit):
                font = self.question_edit.font()
                font.setFamily(font_family)
                self.question_edit.setFont(font)
                
            if hasattr(self, 'answer_edit') and not sip.isdeleted(self.answer_edit):
                font = self.answer_edit.font()
                font.setFamily(font_family)
                self.answer_edit.setFont(font)
                
            logger.debug(f"Font family changed to {font_family}")
        except Exception as e:
            logger.warning(f"Error changing font family: {e}")
    
    def _on_font_size_changed(self, size):
        """Handle font size change."""
        try:
            self.editor_font_size = size
            
            # Update font size in editors
            if hasattr(self, 'question_edit') and not sip.isdeleted(self.question_edit):
                font = self.question_edit.font()
                font.setPointSize(size)
                self.question_edit.setFont(font)
                
            if hasattr(self, 'answer_edit') and not sip.isdeleted(self.answer_edit):
                font = self.answer_edit.font()
                font.setPointSize(size)
                self.answer_edit.setFont(font)
                
            logger.debug(f"Font size changed to {size}")
        except Exception as e:
            logger.warning(f"Error changing font size: {e}")
    
    def _on_highlight_color(self):
        """Open color picker to choose highlight color."""
        try:
            current_color = QColor(self.custom_highlight_color)
            color = QColorDialog.getColor(current_color, self, "Select Highlight Color")
            
            if color.isValid():
                self.custom_highlight_color = color.name()
                self.highlight_color_btn.setStyleSheet(
                    f"background-color: {self.custom_highlight_color}; min-width: 60px; min-height: 24px; border: 1px solid #cccccc; border-radius: 4px;"
                )
                logger.debug(f"Highlight color changed to {self.custom_highlight_color}")
        except Exception as e:
            logger.warning(f"Error setting highlight color: {e}")
    
    def _on_save_editor_settings(self):
        """Save editor settings to global application settings."""
        if not self.settings_manager:
            QMessageBox.warning(self, "Settings Error", "Settings manager not available")
            return
            
        try:
            # Save current settings
            self.settings_manager.set_setting("editor", "font_family", self.editor_font_family)
            self.settings_manager.set_setting("editor", "font_size", self.editor_font_size)
            self.settings_manager.set_setting("editor", "line_height", self.editor_line_height)
            self.settings_manager.set_setting("editor", "highlight_color", self.custom_highlight_color)
            
            # Save settings to disk
            self.settings_manager.save_settings()
            
            QMessageBox.information(self, "Settings Saved", "Editor settings have been saved successfully")
            logger.info("Editor settings saved")
        except Exception as e:
            logger.error(f"Error saving editor settings: {e}")
            QMessageBox.warning(self, "Settings Error", f"Could not save settings: {str(e)}")

    def _safe_disconnect(self, widget, signal_name):
        """Safely disconnect a signal from a widget if possible."""
        if widget is None or sip.isdeleted(widget):
            return
        
        try:
            # Get the signal by name
            if signal_name == 'clicked':
                signal = widget.clicked
            elif signal_name == 'toggled':
                signal = widget.toggled
            elif signal_name == 'currentIndexChanged':
                signal = widget.currentIndexChanged
            elif signal_name == 'itemClicked':
                signal = widget.itemClicked
            elif signal_name == 'textChanged':
                signal = widget.textChanged
            elif signal_name == 'valueChanged':
                signal = widget.valueChanged
            else:
                # Unknown signal
                return
                
            # Disconnect all connections to this signal
            signal.disconnect()
        except (TypeError, RuntimeError, AttributeError) as e:
            # Signal wasn't connected or other error
            logger.debug(f"Error disconnecting {signal_name} from {widget}: {e}")
            pass
            
    @pyqtSlot()
    def _on_mode_changed(self):
        """Handle content generation mode change."""
        # Show/hide provider selection based on mode
        if hasattr(self, 'auto_mode_combo') and hasattr(self, 'provider_container'):
            use_ai = self.auto_mode_combo.currentData() == "ai"
            self.provider_container.setVisible(use_ai)
            
    @pyqtSlot()
    def _on_show_history(self):
        """Show review history dialog."""
        if not self.item:
            return
            
        # Create dialog
        history_dialog = QDialog(self)
        history_dialog.setWindowTitle("Review History")
        history_dialog.resize(600, 300)
        
        # Create layout
        layout = QVBoxLayout(history_dialog)
        
        # Create table
        history_table = QTableWidget()
        history_table.setColumnCount(4)
        history_table.setHorizontalHeaderLabels(["Date", "Grade", "Response Time", "Interval"])
        history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # Load data
        logs = self.db_session.query(ReviewLog).filter(
            ReviewLog.learning_item_id == self.item.id
        ).order_by(ReviewLog.review_date.desc()).all()
        
        # Add rows
        for i, log in enumerate(logs):
            history_table.insertRow(i)
            
            # Date
            date_item = QTableWidgetItem(log.review_date.strftime("%Y-%m-%d %H:%M"))
            history_table.setItem(i, 0, date_item)
            
            # Grade
            grade_item = QTableWidgetItem(str(log.grade))
            
            # Color based on grade
            if log.grade >= 4:
                grade_item.setBackground(QColor(200, 255, 200))  # Light green
            elif log.grade >= 3:
                grade_item.setBackground(QColor(255, 255, 200))  # Light yellow
            else:
                grade_item.setBackground(QColor(255, 200, 200))  # Light red
                
            history_table.setItem(i, 1, grade_item)
            
            # Response time
            if log.response_time:
                time_str = f"{log.response_time / 1000:.1f} sec"
            else:
                time_str = "-"
            time_item = QTableWidgetItem(time_str)
            history_table.setItem(i, 2, time_item)
            
            # Interval
            interval_item = QTableWidgetItem(f"{log.scheduled_interval} days")
            history_table.setItem(i, 3, interval_item)
            
        layout.addWidget(history_table)
        
        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(history_dialog.reject)
        layout.addWidget(button_box)
        
        # Show dialog
        history_dialog.exec()

    # Add the reset_spaced_repetition method to the LearningItem class if it doesn't exist
    if not hasattr(LearningItem, 'reset_spaced_repetition'):
        def _reset_spaced_repetition(self):
            """Reset spaced repetition parameters."""
            self.interval = 0
            self.repetitions = 0
            self.easiness = 2.5
            self.next_review = None
            logger.debug(f"Reset SR parameters for item {self.id}")
            
        # Add the method to the LearningItem class
        setattr(LearningItem, 'reset_spaced_repetition', _reset_spaced_repetition)
            
