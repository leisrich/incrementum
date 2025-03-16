# core/document_processor/summarizer.py

import os
import logging
import tempfile
import json
import re
from typing import Dict, Any, List, Tuple, Optional
import math
import requests
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QTextEdit, QGroupBox,
    QRadioButton, QButtonGroup, QCheckBox, QSpinBox,
    QTabWidget, QMessageBox, QProgressBar, QApplication,
    QWidget, QInputDialog, QLineEdit, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QThread, QObject
from PyQt6.QtGui import QFont

from core.knowledge_base.models import Document, Extract
from core.document_processor.handlers.pdf_handler import PDFHandler
from core.document_processor.handlers.html_handler import HTMLHandler
from core.document_processor.handlers.text_handler import TextHandler
from core.content_extractor.nlp_extractor import NLPExtractor

logger = logging.getLogger(__name__)

# Dictionary of AI provider information
AI_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-3.5-turbo",
        "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
        "max_tokens": 4096,
        "setting_key": "openai_api_key"
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "endpoint": "https://api.anthropic.com/v1/messages",
        "default_model": "claude-3-haiku-20240307",
        "models": ["claude-3-haiku-20240307", "claude-3-sonnet-20240229", "claude-3-opus-20240229"],
        "max_tokens": 4096,
        "setting_key": "anthropic_api_key"
    },
    "openrouter": {
        "name": "OpenRouter",
        "endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "openai/gpt-3.5-turbo",
        "models": ["openai/gpt-3.5-turbo", "anthropic/claude-3-haiku", "anthropic/claude-3-sonnet", "google/gemini-pro"],
        "max_tokens": 4096,
        "setting_key": "openrouter_api_key"
    },
    "google": {
        "name": "Google Gemini",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent",
        "default_model": "gemini-pro",
        "models": ["gemini-pro"],
        "max_tokens": 4096,
        "setting_key": "google_api_key"
    },
    "ollama": {
        "name": "Ollama",
        "endpoint": "http://localhost:11434/api/chat",
        "default_model": "llama3",
        "models": ["llama3", "llama2", "mistral", "codellama", "phi", "gemma:2b", "gemma:7b", "mixtral", "orca-mini"],
        "max_tokens": 4096,
        "setting_key": "ollama_host"
    }
}

class DocumentSummarizer:
    """
    Document summarization module that extracts key information
    and generates summaries at different levels of detail.
    """
    
    def __init__(self, db_session, api_config=None):
        """
        Initialize the summarizer.
        
        Args:
            db_session: Database session
            api_config: Optional API configuration for external AI services
                        Dictionary with keys: provider, api_key, model
        """
        self.db_session = db_session
        self.api_config = api_config or {}
        
        # Initialize handlers
        self.handlers = {
            'pdf': PDFHandler(),
            'html': HTMLHandler(),
            'htm': HTMLHandler(),
            'txt': TextHandler(),
            'text': TextHandler(),
            'jina_web': HTMLHandler(),  # Use HTML handler for Jina web content
        }
        
        # Initialize NLP extractor
        self.nlp_extractor = NLPExtractor(db_session)
        
    def summarize_document(self, document_id: int, level: str = 'medium', 
                           use_ai: bool = True) -> Dict[str, Any]:
        """
        Summarize a document.
        
        Args:
            document_id: Document ID
            level: Summary level ('brief', 'medium', 'detailed')
            use_ai: Whether to use AI for summarization
            
        Returns:
            Dictionary with summary information
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return {"error": "Document not found"}
        
        try:
            # Extract text content
            content = self._extract_document_content(document)
            if not content:
                return {"error": "Failed to extract document content"}
            
            # Determine chunking strategy based on content length
            chunks = self._chunk_content(content, level)
            
            # Process each chunk
            summaries = []
            
            # Configure max workers based on level
            max_workers = 1 if level == 'detailed' else min(len(chunks), 3)
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                if use_ai and self.api_config and self.api_config.get('api_key'):
                    # Use AI-based summarization
                    future_summaries = [executor.submit(self._ai_summarize_chunk, 
                                                      chunk, level) for chunk in chunks]
                    for future in future_summaries:
                        summary = future.result()
                        if summary:
                            summaries.append(summary)
                else:
                    # Use rule-based summarization
                    future_summaries = [executor.submit(self._rule_based_summarize_chunk, 
                                                      chunk, level) for chunk in chunks]
                    for future in future_summaries:
                        summary = future.result()
                        if summary:
                            summaries.append(summary)
            
            # Combine summaries
            combined_summary = self._combine_summaries(summaries, level)
            
            # Extract key concepts
            key_concepts = self.nlp_extractor.identify_key_concepts(content, 
                                                                 num_concepts=10)
            
            # Build result
            result = {
                "document_id": document_id,
                "document_title": document.title,
                "summary_level": level,
                "summary": combined_summary,
                "key_concepts": [concept["text"] for concept in key_concepts],
                "chunk_count": len(chunks),
                "word_count": len(content.split()),
                "summary_word_count": len(combined_summary.split()),
                "compression_ratio": len(combined_summary.split()) / max(1, len(content.split()))
            }
            
            return result
            
        except Exception as e:
            logger.exception(f"Error summarizing document: {e}")
            return {"error": f"Error summarizing document: {str(e)}"}
    
    def extract_key_sections(self, document_id: int, max_sections: int = 5) -> List[Dict[str, Any]]:
        """
        Extract key sections from a document.
        
        Args:
            document_id: Document ID
            max_sections: Maximum number of sections to extract
            
        Returns:
            List of dictionaries with section information
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return []
        
        try:
            # Extract text content
            content = self._extract_document_content(document)
            if not content:
                return []
            
            # Split into sections (using a simple heuristic for demonstration)
            sections = self._split_into_sections(content)
            
            # Score sections for importance
            scored_sections = []
            for i, section in enumerate(sections):
                if not section.strip():
                    continue
                    
                # Score based on several factors
                score = self._score_section_importance(section, i, len(sections))
                
                # Get a title/summary for the section
                title = self._extract_section_title(section) or f"Section {i+1}"
                
                scored_sections.append({
                    "section_id": i,
                    "title": title,
                    "content": section,
                    "importance_score": score,
                    "word_count": len(section.split())
                })
            
            # Sort by importance and limit
            scored_sections.sort(key=lambda x: x["importance_score"], reverse=True)
            top_sections = scored_sections[:max_sections]
            
            # Sort by original order (section_id)
            top_sections.sort(key=lambda x: x["section_id"])
            
            return top_sections
            
        except Exception as e:
            logger.exception(f"Error extracting key sections: {e}")
            return []
    
    def create_summary_extract(self, document_id: int, level: str = 'medium',
                             use_ai: bool = True) -> Optional[int]:
        """
        Create an extract with document summary.
        
        Args:
            document_id: Document ID
            level: Summary level ('brief', 'medium', 'detailed')
            use_ai: Whether to use AI for summarization
            
        Returns:
            Extract ID if successful, None otherwise
        """
        try:
            # Generate summary
            summary_data = self.summarize_document(document_id, level, use_ai)
            
            if "error" in summary_data:
                logger.error(f"Failed to generate summary: {summary_data['error']}")
                return None
            
            # Create extract content
            content = f"# Summary of {summary_data['document_title']}\n\n"
            content += summary_data['summary'] + "\n\n"
            
            # Add key concepts
            content += "## Key Concepts\n\n"
            for concept in summary_data['key_concepts']:
                content += f"- {concept}\n"
            
            # Add metadata
            content += f"\n\n*Summary Level: {level}*\n"
            content += f"*Compression Ratio: {summary_data['compression_ratio']:.2f}*\n"
            
            # Create extract
            from core.content_extractor.extractor import ContentExtractor
            extractor = ContentExtractor(self.db_session)
            
            extract = extractor.create_extract(
                document_id=document_id,
                content=content,
                context=f"Auto-generated {level} summary",
                priority=70,  # Higher priority for summaries
            )
            
            if extract:
                return extract.id
            else:
                return None
                
        except Exception as e:
            logger.exception(f"Error creating summary extract: {e}")
            return None
    
    def _extract_document_content(self, document: Document) -> str:
        """Extract text content from a document."""
        try:
            # Get appropriate handler
            handler = self.handlers.get(document.content_type.lower())
            if not handler:
                logger.error(f"No handler for content type: {document.content_type}")
                return ""
            
            # Extract content
            result = handler.extract_content(document.file_path)
            
            # Return text content
            if isinstance(result, dict) and "text" in result:
                return result["text"]
            elif isinstance(result, str):
                return result
            else:
                logger.error(f"Unexpected content format from handler")
                return ""
                
        except Exception as e:
            logger.exception(f"Error extracting document content: {e}")
            return ""
    
    def _chunk_content(self, content: str, level: str) -> List[str]:
        """Split content into chunks based on level."""
        # Determine chunk size based on level
        if level == 'brief':
            # For brief summaries, use larger chunks (fewer details)
            max_chunk_size = 10000  # characters
        elif level == 'medium':
            max_chunk_size = 5000
        else:  # detailed
            max_chunk_size = 3000  # smaller chunks for more detailed analysis
        
        # Split at natural boundaries (paragraphs)
        paragraphs = re.split(r'\n\s*\n', content)
        
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) > max_chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = paragraph
            else:
                if current_chunk:
                    current_chunk += "\n\n" + paragraph
                else:
                    current_chunk = paragraph
        
        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _ai_summarize_chunk(self, content: str, level: str) -> str:
        """Summarize a chunk of text using AI."""
        if not self.api_config or not self.api_config.get('api_key'):
            return self._rule_based_summarize_chunk(content, level)
        
        try:
            # Configure summarization parameters based on level
            if level == 'brief':
                instruction = "Provide a very concise summary capturing only the most important points."
                max_tokens = 150
            elif level == 'medium':
                instruction = "Provide a balanced summary with main points and important details."
                max_tokens = 300
            else:  # detailed
                instruction = "Provide a comprehensive summary with all important information and key details."
                max_tokens = 500
            
            provider = self.api_config.get('provider', 'openai')
            api_key = self.api_config.get('api_key')
            model = self.api_config.get('model', AI_PROVIDERS[provider]['default_model'])
            
            # Handle different providers
            if provider == 'openai':
                return self._openai_summarize(content, instruction, api_key, model, max_tokens)
            elif provider == 'anthropic':
                return self._anthropic_summarize(content, instruction, api_key, model, max_tokens)
            elif provider == 'openrouter':
                return self._openrouter_summarize(content, instruction, api_key, model, max_tokens)
            elif provider == 'google':
                return self._google_summarize(content, instruction, api_key, model, max_tokens)
            elif provider == 'ollama':
                return self._ollama_summarize(content, instruction, api_key, model, max_tokens)
            else:
                logger.error(f"Unknown AI provider: {provider}")
                return self._rule_based_summarize_chunk(content, level)
                
        except Exception as e:
            logger.exception(f"Error in AI summarization: {e}")
            return self._rule_based_summarize_chunk(content, level)
    
    def _openai_summarize(self, content, instruction, api_key, model, max_tokens):
        """Summarize text using OpenAI's API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"You are a document summarization assistant. {instruction}"},
                {"role": "user", "content": content}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        try:
            response = requests.post(
                AI_PROVIDERS['openai']['endpoint'],
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result["choices"][0]["message"]["content"]
                return summary
            else:
                logger.error(f"OpenAI API request failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.exception(f"Error in OpenAI API request: {e}")
            return None
    
    def _anthropic_summarize(self, content, instruction, api_key, model, max_tokens):
        """Summarize text using Anthropic's Claude API."""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": model,
            "messages": [
                {"role": "user", "content": f"{instruction}\n\n{content}"}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        try:
            response = requests.post(
                AI_PROVIDERS['anthropic']['endpoint'],
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result["content"][0]["text"]
                return summary
            else:
                logger.error(f"Anthropic API request failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.exception(f"Error in Anthropic API request: {e}")
            return None
    
    def _openrouter_summarize(self, content, instruction, api_key, model, max_tokens):
        """Summarize text using OpenRouter API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://incrementum.app"  # Replace with your app domain
        }
        
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"You are a document summarization assistant. {instruction}"},
                {"role": "user", "content": content}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        
        try:
            response = requests.post(
                AI_PROVIDERS['openrouter']['endpoint'],
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result["choices"][0]["message"]["content"]
                return summary
            else:
                logger.error(f"OpenRouter API request failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.exception(f"Error in OpenRouter API request: {e}")
            return None
    
    def _google_summarize(self, content, instruction, api_key, model, max_tokens):
        """Summarize text using Google Gemini API."""
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "contents": [
                {
                    "parts": [
                        {"text": f"You are a document summarization assistant. {instruction}\n\n{content}"}
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.3
            }
        }
        
        try:
            endpoint = f"{AI_PROVIDERS['google']['endpoint']}?key={api_key}"
            response = requests.post(
                endpoint,
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                summary = result["candidates"][0]["content"]["parts"][0]["text"]
                return summary
            else:
                logger.error(f"Google API request failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.exception(f"Error in Google API request: {e}")
            return None
    
    def _ollama_summarize(self, content, instruction, api_key, model, max_tokens):
        """Summarize text using Ollama API."""
        # For Ollama, api_key is actually the host URL (e.g., http://localhost:11434)
        host = api_key
        if not host.startswith('http'):
            host = f"http://{host}"
        if not host.endswith('/api/chat'):
            # Ensure the URL has the correct format
            if host.endswith('/'):
                host = host[:-1]
            if not host.endswith('/api/chat'):
                host = f"{host}/api/chat"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"You are a document summarization assistant. {instruction}"},
                {"role": "user", "content": content}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3,
                "num_predict": max_tokens
            }
        }
        
        try:
            response = requests.post(
                host,
                headers=headers,
                json=data,
                timeout=60  # Longer timeout for local models
            )
            
            if response.status_code == 200:
                result = response.json()
                if "message" in result and "content" in result["message"]:
                    summary = result["message"]["content"]
                    return summary
                else:
                    logger.error(f"Unexpected Ollama API response format: {result}")
                    return None
            elif response.status_code == 404:
                # Model not found, provide a more helpful error message
                error_data = response.json()
                error_msg = error_data.get("error", "Unknown error")
                if "not found" in error_msg:
                    # Check if we can suggest a model
                    base_model = model.split(":")[0] if ":" in model else model
                    try:
                        # Try to get a list of available models
                        model_url = f"{host.replace('/api/chat', '/api/tags')}"
                        models_response = requests.get(model_url, timeout=5)
                        if models_response.status_code == 200:
                            models_data = models_response.json()
                            available_models = []
                            if "models" in models_data:
                                available_models = [m["name"] for m in models_data["models"]]
                            else:
                                available_models = [m["name"] for m in models_data]
                            
                            similar_models = [m for m in available_models if base_model in m]
                            if similar_models:
                                logger.error(f"Model '{model}' not found. Similar models available: {', '.join(similar_models)}")
                            else:
                                logger.error(f"Model '{model}' not found. Try pulling it first with 'ollama pull {model}'")
                        else:
                            logger.error(f"Model '{model}' not found. Try pulling it with 'ollama pull {model}'")
                    except Exception as e:
                        logger.error(f"Model '{model}' not found. Try pulling it with 'ollama pull {model}'")
                else:
                    logger.error(f"Ollama API request failed: {response.status_code} - {response.text}")
                return None
            else:
                logger.error(f"Ollama API request failed: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.exception(f"Error in Ollama API request: {e}")
            return None
    
    def _rule_based_summarize_chunk(self, content: str, level: str) -> str:
        """Summarize a chunk of text using rule-based approaches."""
        try:
            # Handle empty content
            if not content.strip():
                return ""
            
            # Extract sentences
            import nltk
            try:
                sentences = nltk.sent_tokenize(content)
            except:
                # Fallback if NLTK tokenizer fails
                sentences = re.split(r'(?<=[.!?])\s+', content)
            
            if not sentences:
                return ""
            
            # Score sentences based on importance
            sentence_scores = {}
            
            # Get important words/phrases using NLP extractor
            key_concepts = self.nlp_extractor.identify_key_concepts(content, 
                                                                 num_concepts=20)
            important_terms = [concept["text"].lower() for concept in key_concepts]
            
            for i, sentence in enumerate(sentences):
                score = 0
                
                # Position score - first and last sentences are often important
                if i == 0 or i == len(sentences) - 1:
                    score += 0.3
                
                # Length penalty - very short or very long sentences get penalized
                words = sentence.split()
                if len(words) < 5:
                    score -= 0.2
                elif len(words) > 40:
                    score -= 0.1
                
                # Important terms score
                for term in important_terms:
                    if term.lower() in sentence.lower():
                        score += 0.2
                
                # Presence of numbers often indicates important data
                if re.search(r'\d+', sentence):
                    score += 0.1
                
                # Check for indicative phrases
                indicator_phrases = [
                    "in summary", "to summarize", "in conclusion", "to conclude",
                    "importantly", "significantly", "notably", "key", "critical",
                    "essential", "crucial", "primary", "main", "major"
                ]
                
                for phrase in indicator_phrases:
                    if phrase.lower() in sentence.lower():
                        score += 0.2
                
                sentence_scores[i] = score
            
            # Determine how many sentences to keep based on level
            if level == 'brief':
                keep_ratio = 0.15  # Keep 15% of sentences
            elif level == 'medium':
                keep_ratio = 0.3  # Keep 30% of sentences
            else:  # detailed
                keep_ratio = 0.5  # Keep 50% of sentences
            
            # Ensure we keep at least 1 sentence
            num_to_keep = max(1, int(len(sentences) * keep_ratio))
            
            # Get top-scoring sentences
            top_indices = sorted(sentence_scores.keys(), 
                               key=lambda i: sentence_scores[i], reverse=True)[:num_to_keep]
            
            # Sort indices to maintain original order
            top_indices.sort()
            
            # Construct summary
            summary_sentences = [sentences[i] for i in top_indices]
            summary = " ".join(summary_sentences)
            
            return summary
            
        except Exception as e:
            logger.exception(f"Error in rule-based summarization: {e}")
            return ""
    
    def _combine_summaries(self, summaries: List[str], level: str) -> str:
        """Combine multiple chunk summaries into a coherent summary."""
        if not summaries:
            return ""
        
        # For brief summaries, we might want to further condense
        if level == 'brief' and len(summaries) > 1:
            combined = " ".join(summaries)
            return self._rule_based_summarize_chunk(combined, 'brief')
        
        # For medium and detailed, we can join with appropriate transitions
        result = []
        
        for i, summary in enumerate(summaries):
            if i > 0:
                # Add transitions between chunks
                transitions = [
                    "Furthermore, ", "Additionally, ", "Moreover, ",
                    "In addition, ", "Also, ", "Beyond that, ",
                    "Next, ", "Following this, "
                ]
                
                import random
                # Find the first sentence of this summary
                first_sentence = summary.split('. ')[0] + '.'
                
                # If the first sentence is short, add a transition
                if len(first_sentence.split()) < 10:
                    transition = random.choice(transitions)
                    if not summary.startswith(transition):
                        summary = transition + summary[0].lower() + summary[1:]
            
            result.append(summary)
        
        return "\n\n".join(result)
    
    def _split_into_sections(self, content: str) -> List[str]:
        """Split content into logical sections."""
        # Simple approach: split on likely section headers
        # For a real implementation, you'd use more sophisticated approaches
        
        # Try to detect section headers based on common patterns
        section_patterns = [
            # Headers with numbers (e.g., "1. Introduction")
            r'\n\s*\d+\.\s+[A-Z][^.\n]+\n',
            # Headers with "Section" keyword
            r'\n\s*Section\s+\d+[:.]\s*[A-Z][^.\n]+\n',
            # Headers in all caps
            r'\n\s*[A-Z][A-Z\s]+[A-Z]\n',
            # Headers with specific keywords
            r'\n\s*(Introduction|Background|Methods|Results|Discussion|Conclusion|References)[:\s\n]'
        ]
        
        # Apply patterns
        for pattern in section_patterns:
            if re.search(pattern, '\n' + content, re.MULTILINE):
                sections = re.split(pattern, '\n' + content)
                # Remove empty sections and strip whitespace
                sections = [s.strip() for s in sections if s.strip()]
                
                if len(sections) > 1:
                    return sections
        
        # If no section headers found, try splitting by line breaks
        paragraphs = re.split(r'\n\s*\n', content)
        
        # Group paragraphs into reasonable sections
        sections = []
        current_section = ""
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
                
            current_section += paragraph + "\n\n"
            
            # If section gets too large, start a new one
            if len(current_section) > 2000:
                sections.append(current_section.strip())
                current_section = ""
        
        # Add the last section
        if current_section:
            sections.append(current_section.strip())
        
        # If still no sections, just return the whole content as one section
        if not sections:
            return [content.strip()]
        
        return sections
    
    def _score_section_importance(self, section: str, position: int, total_sections: int) -> float:
        """Score a section's importance based on various factors."""
        score = 0.0
        
        # Position-based scoring
        if position == 0:  # Introduction/beginning
            score += 0.8
        elif position == total_sections - 1:  # Conclusion/end
            score += 0.7
        else:
            # Middle sections get scored based on relative position
            relative_pos = position / max(1, total_sections - 1)
            if relative_pos < 0.2 or relative_pos > 0.8:
                score += 0.5  # Near beginning or end
            else:
                score += 0.3  # Middle section
        
        # Content-based scoring
        
        # Length (longer sections might contain more information)
        words = section.split()
        word_count = len(words)
        
        if word_count < 50:
            score += 0.1  # Very short sections might be less important
        elif word_count < 200:
            score += 0.3
        elif word_count < 500:
            score += 0.5
        else:
            score += 0.4  # Very long sections might contain filler
        
        # Presence of key indicator terms
        indicators = [
            "important", "significant", "critical", "key", "main", "essential",
            "conclusion", "result", "finding", "demonstrate", "show", "prove",
            "summary", "therefore", "thus", "in conclusion", "conclude"
        ]
        
        for indicator in indicators:
            if indicator in section.lower():
                score += 0.1
                break  # Only count once
        
        # Presence of numerical data
        if re.search(r'\d+\.\d+|\d+%|\d+\s*\(', section):
            score += 0.2  # Sections with data are often important
        
        # Normalize score to 0-10 range
        return min(10.0, score * 2)
    
    def _extract_section_title(self, section: str) -> Optional[str]:
        """Try to extract a title from a section."""
        # Look for the first line that might be a title
        lines = section.split('\n')
        
        for line in lines[:2]:  # Check first two lines
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
                
            # Check if line looks like a title
            if (len(line) < 100 and  # Not too long
                not line.endswith('.') and  # Doesn't end with period
                line.strip() and  # Not empty
                len(line.split()) < 12):  # Not too many words
                
                return line
                
        # If no title found, use the first sentence
        sentences = nltk.sent_tokenize(section)
        if sentences:
            first_sent = sentences[0]
            # If first sentence is reasonably short, use it
            if len(first_sent) < 100:
                return first_sent
        
        return None


class SummarizeWorker(QObject):
    """Worker thread for document summarization."""
    
    finished = pyqtSignal(dict)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)
    
    def __init__(self, summarizer, document_id, level, use_ai):
        super().__init__()
        self.summarizer = summarizer
        self.document_id = document_id
        self.level = level
        self.use_ai = use_ai
    
    def run(self):
        """Run the summarization task."""
        try:
            # Report initial progress
            self.progress.emit(10)
            
            # Run summarization
            result = self.summarizer.summarize_document(
                self.document_id, self.level, self.use_ai
            )
            
            # Check for errors
            if "error" in result:
                self.error.emit(result["error"])
                return
            
            # Report progress
            self.progress.emit(90)
            
            # Emit result
            self.finished.emit(result)
            
        except Exception as e:
            logger.exception(f"Error in summarization worker: {e}")
            self.error.emit(str(e))


class KeySectionsWorker(QObject):
    """Worker thread for extracting key sections."""
    
    finished = pyqtSignal(list)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)
    
    def __init__(self, summarizer, document_id, max_sections):
        super().__init__()
        self.summarizer = summarizer
        self.document_id = document_id
        self.max_sections = max_sections
    
    def run(self):
        """Run the section extraction task."""
        try:
            # Report initial progress
            self.progress.emit(10)
            
            # Extract key sections
            sections = self.summarizer.extract_key_sections(
                self.document_id, self.max_sections
            )
            
            # Check for errors
            if not sections:
                self.error.emit("No sections found or error extracting sections")
                return
            
            # Report progress
            self.progress.emit(90)
            
            # Emit result
            self.finished.emit(sections)
            
        except Exception as e:
            logger.exception(f"Error in key sections worker: {e}")
            self.error.emit(str(e))


class SummarizeDialog(QDialog):
    """Dialog for summarizing documents."""
    
    extractCreated = pyqtSignal(int)  # extract_id
    
    def __init__(self, db_session, document_id, parent=None):
        super().__init__(parent)
        
        self.db_session = db_session
        self.document_id = document_id
        
        # Initialize document
        self.document = self.db_session.query(Document).get(document_id)
        if not self.document:
            raise ValueError(f"Document not found: {document_id}")
        
        # Get API configuration from settings
        self.api_config = self._get_api_config()
        
        # Initialize summarizer
        self.summarizer = DocumentSummarizer(db_session, self.api_config)
        
        # Initialize UI
        self._create_ui()
        
        # Set window properties
        self.setWindowTitle(f"Summarize Document: {self.document.title}")
        self.resize(800, 600)
    
    def _get_api_config(self):
        """Get API configuration from settings."""
        try:
            # Try to import settings manager
            from core.utils.settings_manager import SettingsManager
            settings = SettingsManager()
            
            # Get provider setting
            provider = settings.get_setting("ai", "provider", "openai")
            
            # Validate provider
            if provider not in AI_PROVIDERS:
                provider = "openai"  # Default to OpenAI if invalid
            
            # Get API key for selected provider
            setting_key = AI_PROVIDERS[provider]["setting_key"]
            
            # Special handling for Ollama which uses host instead of API key
            if provider == "ollama":
                api_key = settings.get_setting("api", setting_key, "http://localhost:11434")
                # If no host is set, check if Ollama is available at default address
                if not api_key or api_key == "":
                    api_key = "http://localhost:11434"
                    
                # For Ollama, we also need to get the model from settings
                model = settings.get_setting("api", "ollama_model", "llama3")
                
                # Try to verify the model exists - if not, fall back to a default that's likely to exist
                try:
                    host = api_key
                    if not host.startswith('http'):
                        host = f"http://{host}"
                    if host.endswith('/'):
                        host = host[:-1]
                    
                    model_url = f"{host}/api/tags"
                    models_response = requests.get(model_url, timeout=5)
                    
                    if models_response.status_code == 200:
                        models_data = models_response.json()
                        available_models = []
                        if "models" in models_data:
                            available_models = [m["name"] for m in models_data["models"]]
                        else:
                            available_models = [m["name"] for m in models_data]
                        
                        # Check if selected model exists
                        if model not in available_models:
                            # Try to find a similar model
                            base_model = model.split(":")[0] if ":" in model else model
                            similar_models = [m for m in available_models if base_model in m]
                            
                            if similar_models:
                                # Use the first similar model
                                logger.warning(f"Model '{model}' not found. Using similar model: {similar_models[0]}")
                                model = similar_models[0]
                            elif available_models:
                                # Fall back to first available model
                                logger.warning(f"Model '{model}' not found. Using available model: {available_models[0]}")
                                model = available_models[0]
                            else:
                                # If no models available, keep the original (will fail later)
                                logger.warning(f"Model '{model}' not found and no alternatives available")
                except Exception as e:
                    logger.warning(f"Could not verify Ollama model availability: {e}")
            else:
                # For other providers, get the API key normally
                api_key = settings.get_setting("api", setting_key, "")
                
                # Get saved model for this provider or use default
                model_setting_key = f"{provider}_model"
                model = settings.get_setting("ai", model_setting_key, AI_PROVIDERS[provider]["default_model"])
            
            # If no API key is found (except for Ollama which has a default), return empty config - will use rule-based summarization
            if not api_key and provider != "ollama":
                return {}
            
            return {
                "provider": provider,
                "api_key": api_key,
                "model": model
            }
            
        except Exception as e:
            logger.exception(f"Error getting API configuration: {e}")
            return {}

    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Document info
        info_label = QLabel(f"<b>Document:</b> {self.document.title}")
        main_layout.addWidget(info_label)
        
        # Create tabs
        tabs = QTabWidget()
        
        # Summary tab
        summary_tab = QWidget()
        self._create_summary_tab(summary_tab)
        tabs.addTab(summary_tab, "Document Summary")
        
        # Key sections tab
        sections_tab = QWidget()
        self._create_sections_tab(sections_tab)
        tabs.addTab(sections_tab, "Key Sections")
        
        main_layout.addWidget(tabs)
        
        # Button row
        button_layout = QHBoxLayout()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        button_layout.addWidget(self.close_button)
        
        main_layout.addLayout(button_layout)
    
    def _create_summary_tab(self, tab):
        """Create the summary tab."""
        layout = QVBoxLayout(tab)
        
        # Options group
        options_group = QGroupBox("Summary Options")
        options_layout = QVBoxLayout(options_group)
        
        # Summary options layout
        summary_options = QHBoxLayout()
        
        # Summary level
        level_label = QLabel("Detail Level:")
        summary_options.addWidget(level_label)
        
        self.level_combo = QComboBox()
        self.level_combo.addItem("Brief", "brief")
        self.level_combo.addItem("Medium", "medium")
        self.level_combo.addItem("Detailed", "detailed")
        self.level_combo.setCurrentIndex(1)  # Medium by default
        summary_options.addWidget(self.level_combo)
        
        # AI option
        self.use_ai_check = QCheckBox("Use AI (if available)")
        self.use_ai_check.setChecked(True)
        summary_options.addWidget(self.use_ai_check)
        
        options_layout.addLayout(summary_options)
        
        # AI Provider options
        ai_provider_group = QGroupBox("AI Provider")
        ai_provider_layout = QFormLayout(ai_provider_group)
        
        self.provider_combo = QComboBox()
        for provider_id, provider_info in AI_PROVIDERS.items():
            self.provider_combo.addItem(provider_info["name"], provider_id)
        
        # Set current provider from settings
        if self.api_config and self.api_config.get("provider"):
            for i in range(self.provider_combo.count()):
                if self.provider_combo.itemData(i) == self.api_config["provider"]:
                    self.provider_combo.setCurrentIndex(i)
                    break
        
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        ai_provider_layout.addRow("Provider:", self.provider_combo)
        
        # Model selection
        self.model_combo = QComboBox()
        self._update_model_combo()
        ai_provider_layout.addRow("Model:", self.model_combo)
        
        # API Key management
        self.api_key_button = QPushButton("Set API Key")
        self.api_key_button.clicked.connect(self._on_set_api_key)
        ai_provider_layout.addRow("API Key:", self.api_key_button)
        
        options_layout.addWidget(ai_provider_group)
        
        # Generate button
        self.generate_button = QPushButton("Generate Summary")
        self.generate_button.clicked.connect(self._on_generate_summary)
        options_layout.addWidget(self.generate_button)
        
        layout.addWidget(options_group)
        
        # Progress bar (initially hidden)
        self.summary_progress = QProgressBar()
        self.summary_progress.setRange(0, 100)
        self.summary_progress.setValue(0)
        self.summary_progress.setVisible(False)
        layout.addWidget(self.summary_progress)
        
        # Results area
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setPlaceholderText("Summary will appear here")
        layout.addWidget(self.summary_text)
        
        # Additional info area
        info_layout = QHBoxLayout()
        
        # Key concepts
        self.concepts_list = QTextEdit()
        self.concepts_list.setReadOnly(True)
        self.concepts_list.setPlaceholderText("Key concepts will appear here")
        self.concepts_list.setMaximumHeight(100)
        info_layout.addWidget(self.concepts_list)
        
        # Create extract button
        self.create_summary_extract_button = QPushButton("Create Extract")
        self.create_summary_extract_button.clicked.connect(self._on_create_summary_extract)
        self.create_summary_extract_button.setEnabled(False)
        info_layout.addWidget(self.create_summary_extract_button)
        
        layout.addLayout(info_layout)
    
    def _create_sections_tab(self, tab):
        """Create the key sections tab."""
        layout = QVBoxLayout(tab)
        
        # Options group
        options_group = QGroupBox("Section Options")
        options_layout = QHBoxLayout(options_group)
        
        # Number of sections
        sections_label = QLabel("Max Sections:")
        options_layout.addWidget(sections_label)
        
        self.sections_spin = QSpinBox()
        self.sections_spin.setRange(1, 20)
        self.sections_spin.setValue(5)
        options_layout.addWidget(self.sections_spin)
        
        # Extract button
        self.extract_sections_button = QPushButton("Extract Key Sections")
        self.extract_sections_button.clicked.connect(self._on_extract_key_sections)
        options_layout.addWidget(self.extract_sections_button)
        
        layout.addWidget(options_group)
        
        # Progress bar (initially hidden)
        self.sections_progress = QProgressBar()
        self.sections_progress.setRange(0, 100)
        self.sections_progress.setValue(0)
        self.sections_progress.setVisible(False)
        layout.addWidget(self.sections_progress)
        
        # Results area
        self.sections_text = QTextEdit()
        self.sections_text.setReadOnly(True)
        self.sections_text.setPlaceholderText("Key sections will appear here")
        layout.addWidget(self.sections_text)
        
        # Create extracts button
        self.create_section_extracts_button = QPushButton("Create Extracts from Sections")
        self.create_section_extracts_button.clicked.connect(self._on_create_section_extracts)
        self.create_section_extracts_button.setEnabled(False)
        layout.addWidget(self.create_section_extracts_button)
    
    @pyqtSlot()
    def _on_generate_summary(self):
        """Handle generate summary button click."""
        # Get options
        level = self.level_combo.currentData()
        use_ai = self.use_ai_check.isChecked()
        
        # If using AI, make sure we have the current settings
        if use_ai:
            provider_id = self.provider_combo.currentData()
            model = self.model_combo.currentData()
            
            # Check if we have an API key
            if not self.api_config or not self.api_config.get("api_key"):
                # Prompt for API key
                self._on_set_api_key()
                
                # If still no API key, disable AI
                if not self.api_config or not self.api_config.get("api_key"):
                    use_ai = False
            elif self.api_config["provider"] != provider_id or self.api_config["model"] != model:
                # Update config with new provider/model
                self.api_config["provider"] = provider_id
                self.api_config["model"] = model
                self.summarizer.api_config = self.api_config
                
                # Save to settings
                from core.utils.settings_manager import SettingsManager
                settings = SettingsManager()
                settings.set_setting("ai", "provider", provider_id)
                model_setting_key = f"{provider_id}_model"
                settings.set_setting("ai", model_setting_key, model)
                settings.save_settings()
        
        # Update UI
        self.generate_button.setEnabled(False)
        self.summary_text.clear()
        self.concepts_list.clear()
        self.create_summary_extract_button.setEnabled(False)
        self.summary_progress.setValue(0)
        self.summary_progress.setVisible(True)
        QApplication.processEvents()
        
        # Create worker thread
        self.summary_thread = QThread()
        self.summary_worker = SummarizeWorker(
            self.summarizer, self.document_id, level, use_ai
        )
        self.summary_worker.moveToThread(self.summary_thread)
        
        # Connect signals
        self.summary_thread.started.connect(self.summary_worker.run)
        self.summary_worker.finished.connect(self._on_summary_finished)
        self.summary_worker.progress.connect(self.summary_progress.setValue)
        self.summary_worker.error.connect(self._on_summary_error)
        self.summary_worker.finished.connect(self.summary_thread.quit)
        self.summary_worker.finished.connect(self.summary_worker.deleteLater)
        self.summary_thread.finished.connect(self.summary_thread.deleteLater)
        
        # Start thread
        self.summary_thread.start()
    
    @pyqtSlot(dict)
    def _on_summary_finished(self, result):
        """Handle summary generation completion."""
        # Update UI
        self.summary_text.setText(result.get('summary', ''))
        
        # Show key concepts
        concepts_text = "\n".join(f"• {concept}" for concept in result.get('key_concepts', []))
        self.concepts_list.setText(concepts_text)
        
        # Store result for extract creation
        self.summary_result = result
        
        # Enable buttons
        self.generate_button.setEnabled(True)
        self.create_summary_extract_button.setEnabled(True)
        self.summary_progress.setVisible(False)
    
    @pyqtSlot(str)
    def _on_summary_error(self, error_msg):
        """Handle summary generation error."""
        # Update UI
        self.summary_text.setText(f"Error: {error_msg}")
        self.generate_button.setEnabled(True)
        self.summary_progress.setVisible(False)
    
    @pyqtSlot()
    def _on_create_summary_extract(self):
        """Handle create summary extract button click."""
        if not hasattr(self, 'summary_result'):
            return
        
        try:
            # Get options
            level = self.level_combo.currentData()
            use_ai = self.use_ai_check.isChecked()
            
            # Create extract
            extract_id = self.summarizer.create_summary_extract(
                self.document_id, level, use_ai
            )
            
            if extract_id:
                QMessageBox.information(
                    self, "Extract Created", 
                    f"Summary extract created successfully."
                )
                
                # Emit signal
                self.extractCreated.emit(extract_id)
            else:
                QMessageBox.warning(
                    self, "Extract Creation Failed", 
                    "Failed to create summary extract."
                )
                
        except Exception as e:
            logger.exception(f"Error creating summary extract: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error creating summary extract: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_extract_key_sections(self):
        """Handle extract key sections button click."""
        # Get options
        max_sections = self.sections_spin.value()
        
        # Update UI
        self.extract_sections_button.setEnabled(False)
        self.sections_text.clear()
        self.create_section_extracts_button.setEnabled(False)
        self.sections_progress.setValue(0)
        self.sections_progress.setVisible(True)
        QApplication.processEvents()
        
        # Create worker thread
        self.sections_thread = QThread()
        self.sections_worker = KeySectionsWorker(
            self.summarizer, self.document_id, max_sections
        )
        self.sections_worker.moveToThread(self.sections_thread)
        
        # Connect signals
        self.sections_thread.started.connect(self.sections_worker.run)
        self.sections_worker.finished.connect(self._on_sections_finished)
        self.sections_worker.progress.connect(self.sections_progress.setValue)
        self.sections_worker.error.connect(self._on_sections_error)
        self.sections_worker.finished.connect(self.sections_thread.quit)
        self.sections_worker.finished.connect(self.sections_worker.deleteLater)
        self.sections_thread.finished.connect(self.sections_thread.deleteLater)
        
        # Start thread
        self.sections_thread.start()
    
    @pyqtSlot(list)
    def _on_sections_finished(self, sections):
        """Handle key sections extraction completion."""
        # Update UI
        self.sections = sections
        
        # Format sections
        text = ""
        for section in sections:
            title = section.get('title', f"Section {section['section_id']+1}")
            score = section.get('importance_score', 0)
            word_count = section.get('word_count', 0)
            
            text += f"## {title}\n"
            text += f"*Score: {score:.1f}/10 | Words: {word_count}*\n\n"
            text += f"{section['content'][:500]}...\n\n"
            text += "-" * 40 + "\n\n"
        
        self.sections_text.setText(text)
        
        # Enable buttons
        self.extract_sections_button.setEnabled(True)
        self.create_section_extracts_button.setEnabled(True)
        self.sections_progress.setVisible(False)
    
    @pyqtSlot(str)
    def _on_sections_error(self, error_msg):
        """Handle key sections extraction error."""
        # Update UI
        self.sections_text.setText(f"Error: {error_msg}")
        self.extract_sections_button.setEnabled(True)
        self.sections_progress.setVisible(False)
    
    @pyqtSlot()
    def _on_create_section_extracts(self):
        """Handle create section extracts button click."""
        if not hasattr(self, 'sections'):
            return
        
        try:
            from core.content_extractor.extractor import ContentExtractor
            extractor = ContentExtractor(self.db_session)
            
            extracts_created = 0
            
            for section in self.sections:
                title = section.get('title', f"Section {section['section_id']+1}")
                
                # Create extract
                extract = extractor.create_extract(
                    document_id=self.document_id,
                    content=section['content'],
                    context=f"Key section: {title}",
                    priority=min(int(section['importance_score'] * 10), 100),
                )
                
                if extract:
                    extracts_created += 1
                    # Emit signal for first extract only
                    if extracts_created == 1:
                        self.extractCreated.emit(extract.id)
            
            if extracts_created > 0:
                QMessageBox.information(
                    self, "Extracts Created", 
                    f"Created {extracts_created} extracts from key sections."
                )
            else:
                QMessageBox.warning(
                    self, "No Extracts Created", 
                    "Failed to create extracts from sections."
                )
                
        except Exception as e:
            logger.exception(f"Error creating section extracts: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error creating section extracts: {str(e)}"
            )

    @pyqtSlot(int)
    def _on_provider_changed(self, index):
        """Handle provider selection change."""
        self._update_model_combo()
    
    @pyqtSlot()
    def _on_set_api_key(self):
        """Handle API key setting button click."""
        provider_id = self.provider_combo.currentData()
        provider_name = self.provider_combo.currentText()
        
        from core.utils.settings_manager import SettingsManager
        settings = SettingsManager()
        
        setting_key = AI_PROVIDERS[provider_id]["setting_key"]
        current_key = settings.get_setting("ai", setting_key, "")
        
        # Special handling for Ollama
        if provider_id == "ollama":
            # For Ollama, we need the host URL rather than an API key
            current_key = settings.get_setting("api", setting_key, "http://localhost:11434")
            
            api_key, ok = QInputDialog.getText(
                self, f"Set {provider_name} Host", 
                f"Enter your {provider_name} host URL (default: http://localhost:11434):",
                QLineEdit.EchoMode.Normal,
                text=current_key
            )
            
            if ok:
                # If empty, use default
                if not api_key:
                    api_key = "http://localhost:11434"
                
                # Save to settings
                settings.set_setting("api", setting_key, api_key)
                
                # Get and save model as well
                model = self.model_combo.currentData()
                settings.set_setting("api", "ollama_model", model)
                
                settings.save_settings()
                
                # Update API configuration
                self.api_config = {
                    "provider": provider_id,
                    "api_key": api_key,
                    "model": model
                }
                
                # Update summarizer
                self.summarizer.api_config = self.api_config
            
            return
        
        # Regular API key handling for other providers
        # Mask key for display
        masked_key = "****" + current_key[-4:] if current_key and len(current_key) > 4 else ""
        hint_text = f"Current: {masked_key}" if masked_key else "No API key set"
        
        api_key, ok = QInputDialog.getText(
            self, f"Set {provider_name} API Key", 
            f"Enter your {provider_name} API key for AI-powered summarization:\n{hint_text}",
            QLineEdit.EchoMode.Password
        )
        
        if ok and api_key:
            # Save to settings
            settings.set_setting("ai", "provider", provider_id)
            settings.set_setting("ai", setting_key, api_key)
            
            # Save selected model
            model = self.model_combo.currentData()
            model_setting_key = f"{provider_id}_model"
            settings.set_setting("ai", model_setting_key, model)
            
            settings.save_settings()
            
            # Update API configuration
            self.api_config = {
                "provider": provider_id,
                "api_key": api_key,
                "model": model
            }
            
            # Update summarizer
            self.summarizer.api_config = self.api_config

    def _update_model_combo(self):
        """Update the model combo box based on selected provider."""
        provider_id = self.provider_combo.currentData()
        self.model_combo.clear()
        
        if provider_id in AI_PROVIDERS:
            # Special handling for Ollama to check for available models
            if provider_id == "ollama":
                from core.utils.settings_manager import SettingsManager
                settings = SettingsManager()
                
                # Try to get available models from Ollama if possible
                host = settings.get_setting("api", "ollama_host", "http://localhost:11434")
                if not host.startswith("http"):
                    host = f"http://{host}"
                if host.endswith('/'):
                    host = host[:-1]
                
                try:
                    # Try to get models list from Ollama
                    import requests
                    response = requests.get(f"{host}/api/tags", timeout=2)
                    if response.status_code == 200:
                        # Add models from Ollama
                        models_data = response.json()
                        if "models" in models_data:
                            # New API format
                            available_models = [m["name"] for m in models_data["models"]]
                        else:
                            # Old API format
                            available_models = [m["name"] for m in models_data]
                            
                        for model in available_models:
                            self.model_combo.addItem(model, model)
                    else:
                        # Fallback to default list
                        for model in AI_PROVIDERS[provider_id]["models"]:
                            self.model_combo.addItem(model, model)
                except Exception as e:
                    logger.warning(f"Failed to get Ollama models: {e}")
                    # Fallback to default list on error
                    for model in AI_PROVIDERS[provider_id]["models"]:
                        self.model_combo.addItem(model, model)
            else:
                # Regular providers - use the predefined list
                for model in AI_PROVIDERS[provider_id]["models"]:
                    self.model_combo.addItem(model, model)
            
            # Set current model from settings if available
            if self.api_config and self.api_config.get("provider") == provider_id and self.api_config.get("model"):
                model_to_set = self.api_config["model"]
                
                # For Ollama, we might need to load from api settings
                if provider_id == "ollama" and not model_to_set:
                    from core.utils.settings_manager import SettingsManager
                    settings = SettingsManager()
                    model_to_set = settings.get_setting("api", "ollama_model", "llama3")
                
                # Find and set the model in the combo box
                for i in range(self.model_combo.count()):
                    if self.model_combo.itemData(i) == model_to_set:
                        self.model_combo.setCurrentIndex(i)
                        break
                
                # If model not found, add it and select it
                if self.model_combo.currentData() != model_to_set and model_to_set:
                    self.model_combo.addItem(model_to_set, model_to_set)
                    self.model_combo.setCurrentIndex(self.model_combo.count() - 1)
