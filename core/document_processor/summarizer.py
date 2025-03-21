#!/usr/bin/env python3
# core/document_processor/summarizer.py

import os
import logging
import tempfile
import json
import re
import time
import threading
from typing import Dict, Any, List, Tuple, Optional
import math
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QTextEdit, QGroupBox,
    QRadioButton, QButtonGroup, QCheckBox, QSpinBox,
    QTabWidget, QMessageBox, QProgressBar, QApplication,
    QWidget, QInputDialog, QLineEdit, QFormLayout,
    QSplitter, QSlider, QPlainTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QThread, QObject
from PyQt6.QtGui import QFont, QIcon

from core.knowledge_base.models import Document, Extract
from core.document_processor.handlers.pdf_handler import PDFHandler
from core.document_processor.handlers.html_handler import HTMLHandler
from core.document_processor.handlers.text_handler import TextHandler
from core.content_extractor.nlp_extractor import NLPExtractor

logger = logging.getLogger(__name__)

# Define AI providers
AI_PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "setting_key": "openai_api_key",
        "models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo", "gpt-4o"],
        "endpoint": "https://api.openai.com/v1/chat/completions"
    },
    "anthropic": {
        "name": "Anthropic",
        "setting_key": "anthropic_api_key",
        "models": ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
        "endpoint": "https://api.anthropic.com/v1/messages"
    },
    "google": {
        "name": "Google",
        "setting_key": "google_api_key",
        "models": ["gemini-pro", "gemini-ultra"],
        "endpoint": "https://generativelanguage.googleapis.com/v1"
    },
    "openrouter": {
        "name": "OpenRouter",
        "setting_key": "openrouter_api_key",
        "models": ["openai/gpt-3.5-turbo", "anthropic/claude-3-opus", "google/gemini-pro", "meta/llama-3-70b"],
        "endpoint": "https://openrouter.ai/api/v1/chat/completions"
    },
    "ollama": {
        "name": "Ollama",
        "setting_key": "ollama_host",
        "models": ["llama3", "mistral", "mixtral", "phi3", "wizard"],
        "endpoint": "/api/chat"
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
            logger.warning("No API configuration available. Falling back to rule-based summarization.")
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
            model = self.api_config.get('model', 'gpt-3.5-turbo')
            
            if not api_key:
                logger.warning(f"No API key provided for {provider}. Falling back to rule-based summarization.")
                return self._rule_based_summarize_chunk(content, level)
            
            logger.info(f"Using {provider} with model {model} for summarization")
            
            # Handle different providers
            summary = None
            if provider == 'openai':
                summary = self._openai_summarize(content, instruction, api_key, model, max_tokens)
            elif provider == 'anthropic':
                summary = self._anthropic_summarize(content, instruction, api_key, model, max_tokens)
            elif provider == 'openrouter':
                summary = self._openrouter_summarize(content, instruction, api_key, model, max_tokens)
            elif provider == 'google':
                summary = self._google_summarize(content, instruction, api_key, model, max_tokens)
            elif provider == 'ollama':
                summary = self._ollama_summarize(content, instruction, api_key, model, max_tokens)
            else:
                logger.error(f"Unknown AI provider: {provider}")
                return f"Error: Unknown AI provider '{provider}'"
            
            # Check for errors
            if summary is None:
                logger.error(f"API call to {provider} failed to return a summary")
                return f"Error: Failed to get summary from {provider}"
            
            # Check if the summary starts with "Error:"
            if isinstance(summary, str) and summary.startswith("Error:"):
                logger.error(f"API error: {summary}")
                return summary
                
            return summary
                
        except Exception as e:
            error_msg = f"Error in AI summarization: {str(e)}"
            logger.exception(error_msg)
            return f"Error: {error_msg}"
    
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
            # Construct the proper endpoint for the correct model
            endpoint = f"{AI_PROVIDERS['google']['endpoint']}/models/{model}:generateContent?key={api_key}"
            logger.info(f"Using Google endpoint: {endpoint.split('?')[0]}")
            
            response = requests.post(
                endpoint,
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if "candidates" in result and len(result["candidates"]) > 0:
                    summary = result["candidates"][0]["content"]["parts"][0]["text"]
                    return summary
                else:
                    logger.error(f"Unexpected Google API response format: {result}")
                    return f"Error: Unexpected Google API response format"
            else:
                logger.error(f"Google API request failed: {response.status_code} - {response.text}")
                if response.status_code == 404:
                    return f"Error: Model '{model}' not found. Please verify the model name is correct."
                return f"Error: Google API request failed with status {response.status_code}"
        except Exception as e:
            logger.exception(f"Error in Google API request: {e}")
            return f"Error: {str(e)}"
    
    def _ollama_summarize(self, content, instruction, api_key, model, max_tokens):
        """Summarize text using Ollama API."""
        # For Ollama, api_key is actually the host URL (e.g., http://localhost:11434)
        host = api_key
        if not host.startswith('http'):
            host = f"http://{host}"
            
        # Remove trailing slash if present
        if host.endswith('/'):
            host = host[:-1]
            
        # Construct the endpoint URL
        endpoint = f"{host}{AI_PROVIDERS['ollama']['endpoint']}"
        
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
            logger.info(f"Sending request to Ollama at {endpoint} with model {model}")
            
            # Use significantly longer timeout for Ollama to prevent timeouts
            response = requests.post(
                endpoint,
                headers=headers,
                json=data,
                timeout=180  # Increase to 3 minutes for local models which may take longer
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Received successful response from Ollama")
                
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
                if "not found" in error_msg.lower():
                    logger.error(f"Model '{model}' not found. Try pulling it with 'ollama pull {model}'")
                    return f"Error: Model '{model}' not found. Please run 'ollama pull {model}' to download it first."
                else:
                    logger.error(f"Ollama API request failed: {response.status_code} - {response.text}")
                    return f"Error: {error_msg}"
            else:
                logger.error(f"Ollama API request failed: {response.status_code} - {response.text}")
                response_text = response.text[:500]  # Truncate long responses
                return f"Error: Ollama API request failed with status {response.status_code}: {response_text}"
        except requests.exceptions.ReadTimeout:
            error_msg = f"Timeout while waiting for Ollama response. The model '{model}' may be too large or loading for the first time."
            logger.error(error_msg)
            return f"Error: {error_msg} Try again or use a different model."
        except requests.exceptions.ConnectionError:
            error_msg = f"Could not connect to Ollama at {host}. Make sure Ollama is running."
            logger.error(error_msg)
            return f"Error: {error_msg} Check if the Ollama server is running at {host}."
        except Exception as e:
            logger.exception(f"Error in Ollama API request: {e}")
            return f"Error: {str(e)}"
    
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
        
        # Check if any summary contains an error message
        for summary in summaries:
            if summary.startswith("Error:"):
                # Return the first error message we find
                return summary
        
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
        """Initialize the summarize dialog."""
        super().__init__(parent)
        self.setWindowTitle("Document Summary")
        self.resize(800, 600)
        self.document_id = document_id
        self.db_session = db_session
        self.summarizer = None
        self.worker_thread = None
        self.worker = None
        self.sections_thread = None
        self.sections_worker = None
        self.sections = None
        
        # Set default font to system font to avoid font issues
        font = QApplication.font()
        self.setFont(font)
        
        # Get API configuration from settings
        self.api_config = self._get_api_config()
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Get document
        self.document = db_session.query(Document).get(document_id)
        if not self.document:
            raise ValueError(f"Document with ID {document_id} not found.")
        
        # Create summarizer manager
        from core.document_processor.summarizer_manager import SummarizerManager
        self.summarizer = SummarizerManager(db_session)
        
        # Create form layout for options
        options_group = QGroupBox("Summarization Options")
        options_layout = QFormLayout(options_group)
        
        # Provider selection
        self.provider_combo = QComboBox()
        self.available_providers = []
        
        # Add providers with their IDs as data
        for provider_id, provider_info in AI_PROVIDERS.items():
            self.provider_combo.addItem(provider_info["name"], provider_id)
            self.available_providers.append(provider_info["name"])
            
        # Set current provider from settings
        current_provider = self.api_config.get("provider", "openai")
        for i in range(self.provider_combo.count()):
            if self.provider_combo.itemData(i) == current_provider:
                self.provider_combo.setCurrentIndex(i)
                break
                
        options_layout.addRow("Provider:", self.provider_combo)
        
        # Update models when provider changes
        self.provider_combo.currentIndexChanged.connect(self._update_model_combo)
        
        # Model selection
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)  # Allow custom model names
        options_layout.addRow("Model:", self.model_combo)
        
        # Temperature
        self.temperature_slider = QSlider(Qt.Orientation.Horizontal)
        self.temperature_slider.setMinimum(0)
        self.temperature_slider.setMaximum(100)
        self.temperature_slider.setValue(70)  # Default to 0.7
        self.temperature_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.temperature_slider.setTickInterval(10)
        self.temperature_value = QLabel("0.7")
        temp_layout = QHBoxLayout()
        temp_layout.addWidget(self.temperature_slider)
        temp_layout.addWidget(self.temperature_value)
        options_layout.addRow("Temperature:", temp_layout)
        self.temperature_slider.valueChanged.connect(self._on_temperature_changed)
        
        # Length of summary
        self.length_combo = QComboBox()
        self.length_combo.addItems(["Short", "Medium", "Long", "Very Long"])
        self.length_combo.setCurrentIndex(1)  # Default to medium
        options_layout.addRow("Length:", self.length_combo)
        
        # Maximum tokens
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setMinimum(100)
        self.max_tokens_spin.setMaximum(100000)
        self.max_tokens_spin.setValue(4000)
        self.max_tokens_spin.setSingleStep(100)
        options_layout.addRow("Max Tokens:", self.max_tokens_spin)
        
        # Style selection
        self.style_combo = QComboBox()
        self.style_combo.addItems([
            "Concise and Factual", 
            "Comprehensive and Detailed",
            "Academic and Formal",
            "Simple and Accessible", 
            "Critical Analysis",
            "Key Points and Takeaways"
        ])
        options_layout.addRow("Style:", self.style_combo)
        
        # Add options group to layout
        layout.addWidget(options_group)
        
        # Summary display
        summary_group = QGroupBox("Summary")
        self.summary_layout = QVBoxLayout(summary_group)
        
        # Summary text area
        self.summary_text = QPlainTextEdit()
        self.summary_text.setReadOnly(False)  # Allow editing
        self.summary_layout.addWidget(self.summary_text)
        
        # Create extract button
        create_extract_button = QPushButton("Create Extract from Selection")
        create_extract_button.clicked.connect(self._on_create_summary_extract)
        self.summary_layout.addWidget(create_extract_button)
        
        # Add summary group to layout
        layout.addWidget(summary_group)
        
        # Status and progress
        status_layout = QHBoxLayout()
        self.status_label = QLabel("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        layout.addLayout(status_layout)
        
        # Buttons
        bottom_buttons = QHBoxLayout()
        
        # Generate button
        self.generate_button = QPushButton("Generate Summary")
        self.generate_button.clicked.connect(self._on_generate_summary)
        bottom_buttons.addWidget(self.generate_button)
        
        # Extract key sections button
        self.extract_sections_button = QPushButton("Extract Key Sections")
        self.extract_sections_button.clicked.connect(self._on_extract_key_sections)
        bottom_buttons.addWidget(self.extract_sections_button)
        
        # Add buttons to layout
        layout.addLayout(bottom_buttons)
        
        # Initialize UI with first provider's models
        self._update_model_combo()
    
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
            
            # Get API key for selected provider - each provider has its own setting key
            setting_key = AI_PROVIDERS[provider]["setting_key"]
            
            # Get the correct API key based on the provider
            if provider == "openai":
                api_key = settings.get_setting("api", "openai_api_key", "")
            elif provider == "anthropic":
                api_key = settings.get_setting("api", "anthropic_api_key", "")
            elif provider == "google":
                api_key = settings.get_setting("api", "google_api_key", "")
            elif provider == "openrouter":
                api_key = settings.get_setting("api", "openrouter_api_key", "")
            elif provider == "ollama":
                api_key = settings.get_setting("api", "ollama_host", "http://localhost:11434")
                # If no host is set, use the default localhost
                if not api_key or api_key == "":
                    api_key = "http://localhost:11434"
            else:
                api_key = ""
                
            # Get model for the provider
            if provider == "openai":
                model = settings.get_setting("api", "openai_model", "gpt-3.5-turbo")
            elif provider == "anthropic":
                model = settings.get_setting("api", "anthropic_model", "claude-3-haiku-20240307")
            elif provider == "google":
                model = settings.get_setting("api", "google_model", "gemini-pro")
            elif provider == "openrouter":
                model = settings.get_setting("api", "openrouter_model", "openai/gpt-3.5-turbo")
            elif provider == "ollama":
                model = settings.get_setting("api", "ollama_model", "llama3")
            else:
                # Default to first model if available
                available_models = AI_PROVIDERS[provider].get("models", [])
                model = available_models[0] if available_models else ""
            
            # Log selected provider and model
            logger.info(f"Using provider '{provider}' with model '{model}'")
            if provider == "ollama":
                logger.info(f"Ollama host set to: {api_key}")
            
            # Build config dictionary
            return {
                "provider": provider,
                "api_key": api_key,
                "model": model
            }
            
        except Exception as e:
            logger.exception(f"Error getting API configuration: {e}")
            return {}
    
    def _update_model_combo(self):
        """Update the model combo box based on selected provider."""
        # Get the provider ID from the current item's data
        provider_id = self.provider_combo.currentData()
        
        # Save current text before clearing
        current_text = self.model_combo.currentText()
        self.model_combo.clear()
        
        # Get models for the provider
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
            
            # Add placeholder for custom model
            if self.model_combo.count() > 0 and not self.model_combo.itemText(self.model_combo.count() - 1).startswith("-- Custom"):
                self.model_combo.insertSeparator(self.model_combo.count())
                self.model_combo.addItem("-- Custom Model --", "custom")
            
            # Set model from settings if available
            model_to_set = ""
            
            # Try to get model from API config
            if self.api_config and self.api_config.get("provider") == provider_id and self.api_config.get("model"):
                model_to_set = self.api_config["model"]
            
            # Otherwise try to get from settings
            if not model_to_set:
                from core.utils.settings_manager import SettingsManager
                settings = SettingsManager()
                if provider_id == "ollama":
                    model_to_set = settings.get_setting("api", "ollama_model", "")
                else:
                    model_to_set = settings.get_setting("api", f"{provider_id}_model", "")
            
            # If we have a model from settings, set it
            if model_to_set:
                # Check if the model is in the list
                index = -1
                for i in range(self.model_combo.count()):
                    if self.model_combo.itemText(i) == model_to_set:
                        index = i
                        break
                
                if index >= 0:
                    self.model_combo.setCurrentIndex(index)
                else:
                    # Custom model - set the text directly
                    self.model_combo.setCurrentText(model_to_set)
            elif current_text and current_text.strip():
                # If we had a custom text previously, restore it
                self.model_combo.setCurrentText(current_text)

    def _on_generate_summary(self):
        """Handle generate summary button click."""
        # Get options from length combo and other available controls
        length_map = {
            0: "brief",    # Short
            1: "medium",   # Medium
            2: "detailed", # Long
            3: "detailed"  # Very Long
        }
        level = length_map.get(self.length_combo.currentIndex(), "medium")
        
        # Always use AI since we have the UI elements for it
        use_ai = True
        
        # Get provider information
        provider_id = self.provider_combo.currentData()
        provider_name = self.provider_combo.currentText()
        
        if not provider_id:
            # Default to first provider if not found
            provider_id = list(AI_PROVIDERS.keys())[0]
            logger.warning(f"No valid provider ID found, defaulting to {provider_id}")
        
        # Get model from text since we have an editable combo
        model = self.model_combo.currentText().strip()
        
        if not model:
            # If empty, use first item in the predefined models list
            if provider_id in AI_PROVIDERS and AI_PROVIDERS[provider_id]["models"]:
                model = AI_PROVIDERS[provider_id]["models"][0]
                self.model_combo.setCurrentText(model)
        
        # Check if we have an API key
        if not self.api_config or not self.api_config.get("api_key"):
            # Prompt for API key
            self._on_set_api_key()
            
            # If still no API key, disable AI
            if not self.api_config or not self.api_config.get("api_key"):
                use_ai = False
                self.status_label.setText("No API key set. Using rule-based summarization.")
                self.status_label.setStyleSheet("color: orange")
        elif self.api_config["provider"] != provider_id or self.api_config["model"] != model:
            # Update config with new provider/model
            self.api_config["provider"] = provider_id
            self.api_config["model"] = model
            self.summarizer.summarizer.api_config = self.api_config
            
            # Save to settings
            from core.utils.settings_manager import SettingsManager
            settings = SettingsManager()
            settings.set_setting("ai", "provider", provider_id)
            model_setting_key = f"{provider_id}_model"
            settings.set_setting("api", model_setting_key, model)
            settings.save_settings()
        
        # Update UI
        self.generate_button.setEnabled(False)
        self.summary_text.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Generating summary...")
        self.status_label.setStyleSheet("")
        QApplication.processEvents()
        
        # Ensure any previous threads are cleaned up
        try:
            if hasattr(self, 'summary_thread') and self.summary_thread is not None:
                if self.summary_thread.isRunning():
                    self.summary_thread.quit()
                    self.summary_thread.wait(1000)  # Wait up to 1 second
        except RuntimeError:
            # Handle case where thread might have been deleted
            logger.warning("Summary thread was already deleted during closeEvent")
        except Exception as e:
            logger.warning(f"Error cleaning up summary thread during closeEvent: {e}")
            
        # Create worker thread
        self.summary_thread = QThread()
        self.summary_worker = SummarizeWorker(
            self.summarizer, self.document_id, level, use_ai
        )
        self.summary_worker.moveToThread(self.summary_thread)
        
        # Connect signals
        self.summary_thread.started.connect(self.summary_worker.run)
        self.summary_worker.finished.connect(self._on_summary_finished)
        self.summary_worker.progress.connect(self.progress_bar.setValue)
        self.summary_worker.error.connect(self._on_summary_error)
        self.summary_worker.finished.connect(self.summary_thread.quit)
        self.summary_worker.finished.connect(lambda: self.summary_worker.deleteLater())
        self.summary_thread.finished.connect(lambda: self.summary_thread.deleteLater())
        
        # Start thread
        self.summary_thread.start()
    
    @pyqtSlot(dict)
    def _on_summary_finished(self, result):
        """Handle summary generation finished."""
        # Update UI
        self.summary_text.setPlainText(result.get('summary', ''))
        
        # Store result for extract creation
        self.summary_result = result
        
        # Enable buttons
        self.generate_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Summary generated successfully")
        self.status_label.setStyleSheet("color: green")
        QApplication.processEvents()
    
    @pyqtSlot(str)
    def _on_summary_error(self, error_msg):
        """Handle summary generation error."""
        error_text = f"Error: {error_msg}"
        
        # Format the error message with more details for common errors
        if "ollama" in error_msg.lower() and "not found" in error_msg.lower():
            model = self.model_combo.currentText()
            error_text += f"\n\nTo fix this, you need to pull the model with the command:\n\nollama pull {model}"
        elif "connection" in error_msg.lower() and "ollama" in error_msg.lower():
            error_text += "\n\nMake sure the Ollama server is running by executing 'ollama serve' in a terminal."
        elif "api key" in error_msg.lower():
            provider = self.provider_combo.currentText()
            error_text += f"\n\nYou need to set up your {provider} API key in the settings."
        
        self.summary_text.setPlainText(error_text)
        self.generate_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {error_msg}")
        self.status_label.setStyleSheet("color: red")
        QApplication.processEvents()
        
        # Show a message box for critical errors
        if "not found" in error_msg.lower() or "connection" in error_msg.lower() or "api key" in error_msg.lower():
            QMessageBox.warning(self, "Summarization Error", error_text)
    
    @pyqtSlot()
    def _on_create_summary_extract(self):
        """Handle create extract from summary selection."""
        try:
            # Get selected text
            cursor = self.summary_text.textCursor()
            selected_text = cursor.selectedText()
            
            if not selected_text:
                QMessageBox.information(
                    self, "No Selection", 
                    "Please select text in the summary to create an extract."
                )
                return
            
            # Create new extract from selection
            extract = Extract(
                content=selected_text,
                document_id=self.document_id,
                context=f"Summary Extract: {self.document.title[:50]}...",
                created_date=datetime.now(),
                last_reviewed=datetime.now(),
                position=json.dumps({
                    "source": "summary",
                    "text": selected_text[:100]  # Store start of text for context
                })
            )
            
            # Add to database
            self.db_session.add(extract)
            self.db_session.commit()
            
            # Get the ID of the newly created extract
            extract_id = extract.id
            
            # Inform user
            QMessageBox.information(
                self, "Extract Created", 
                f"Extract created successfully from summary selection."
            )
            
            # Emit signal with new extract ID (not the extract object)
            self.extractCreated.emit(extract_id)
                
        except Exception as e:
            logger.exception(f"Error creating extract from selection: {e}")
            QMessageBox.warning(
                self, "Error", 
                f"Error creating extract: {str(e)}"
            )
    
    @pyqtSlot()
    def _on_extract_key_sections(self):
        """Handle extract key sections button click."""
        # Default max sections
        max_sections = 5
        
        # Update UI
        self.extract_sections_button.setEnabled(False)
        self.summary_text.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.status_label.setText("Extracting key sections...")
        self.status_label.setStyleSheet("")
        QApplication.processEvents()
        
        # Ensure any previous threads are cleaned up
        try:
            if hasattr(self, 'sections_thread') and self.sections_thread is not None:
                if self.sections_thread.isRunning():
                    self.sections_thread.quit()
                    self.sections_thread.wait(1000)  # Wait up to 1 second
        except RuntimeError:
            # Handle case where thread might have been deleted
            logger.warning("Sections thread was already deleted during closeEvent")
        except Exception as e:
            logger.warning(f"Error cleaning up sections thread during closeEvent: {e}")
            
        # Create worker thread
        self.sections_thread = QThread()
        self.sections_worker = KeySectionsWorker(
            self.summarizer, self.document_id, max_sections
        )
        self.sections_worker.moveToThread(self.sections_thread)
        
        # Connect signals
        self.sections_thread.started.connect(self.sections_worker.run)
        self.sections_worker.finished.connect(self._on_sections_finished)
        self.sections_worker.progress.connect(self.progress_bar.setValue)
        self.sections_worker.error.connect(self._on_sections_error)
        self.sections_worker.finished.connect(self.sections_thread.quit)
        self.sections_worker.finished.connect(lambda: self.sections_worker.deleteLater())
        self.sections_thread.finished.connect(lambda: self.sections_thread.deleteLater())
        
        # Start thread
        self.sections_thread.start()
    
    @pyqtSlot(list)
    def _on_sections_finished(self, sections):
        """Handle key sections extraction finished."""
        if not sections:
            self._on_sections_error("No sections were extracted")
            return
            
        # Store sections for later extraction
        self.sections = sections
        
        # Sort sections by importance
        sections.sort(key=lambda x: x['importance_score'], reverse=True)
        
        # Format sections for display
        sections_text = []
        for i, section in enumerate(sections):
            title = section.get('title', f"Section {section['section_id']+1}")
            importance = int(section['importance_score'] * 100)
            
            sections_text.append(f"## {title}")
            sections_text.append(f"Importance: {importance}%")
            sections_text.append("")
            sections_text.append(section['content'])
            sections_text.append("")
        
        # Update UI with sections
        self.summary_text.setPlainText("\n".join(sections_text))
        self.extract_sections_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Key sections extracted successfully")
        self.status_label.setStyleSheet("color: green")
        QApplication.processEvents()
    
    @pyqtSlot(str)
    def _on_sections_error(self, error_msg):
        """Handle key sections extraction error."""
        error_text = f"Error: {error_msg}"
        
        # Format the error message with more details for common errors
        if "ollama" in error_msg.lower() and "not found" in error_msg.lower():
            model = self.model_combo.currentText()
            error_text += f"\n\nTo fix this, you need to pull the model with the command:\n\nollama pull {model}"
        elif "connection" in error_msg.lower() and "ollama" in error_msg.lower():
            error_text += "\n\nMake sure the Ollama server is running by executing 'ollama serve' in a terminal."
        elif "api key" in error_msg.lower():
            provider = self.provider_combo.currentText()
            error_text += f"\n\nYou need to set up your {provider} API key in the settings."
        
        # Update UI
        self.summary_text.setPlainText(error_text)
        self.extract_sections_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"Error: {error_msg}")
        self.status_label.setStyleSheet("color: red")
        QApplication.processEvents()
        
        # Show a message box for critical errors
        if "not found" in error_msg.lower() or "connection" in error_msg.lower() or "api key" in error_msg.lower():
            QMessageBox.warning(self, "Section Extraction Error", error_text)
    
    @pyqtSlot()
    def _on_create_section_extracts(self):
        """Handle create section extracts button click."""
        if not hasattr(self, 'sections') or not self.sections:
            QMessageBox.warning(
                self, "No Sections", 
                "No sections available to create extracts from."
            )
            return
        
        try:
            from core.content_extractor.extractor import ContentExtractor
            extractor = ContentExtractor(self.db_session)
            
            extracts_created = 0
            first_extract_id = None
            
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
                    # Store the ID of the first extract
                    if extracts_created == 1:
                        first_extract_id = extract.id
            
            # Emit signal for the first extract ID (if any extracts were created)
            if first_extract_id is not None:
                self.extractCreated.emit(first_extract_id)
            
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

    @pyqtSlot()
    def _on_set_api_key(self):
        """Handle API key setting button click."""
        provider_id = self.provider_combo.currentData()
        provider_name = self.provider_combo.currentText()
        
        if not provider_id or provider_id not in AI_PROVIDERS:
            QMessageBox.warning(self, "Invalid Provider", f"The selected provider '{provider_name}' is not valid.")
            return
        
        from core.utils.settings_manager import SettingsManager
        settings = SettingsManager()
        
        # Get the current API key based on the provider
        setting_key = AI_PROVIDERS[provider_id]["setting_key"]
        
        # Get the correct key based on the provider
        if provider_id == "openai":
            current_api_key = settings.get_setting("api", "openai_api_key", "")
            prompt_text = "Enter your OpenAI API key:"
            window_title = "OpenAI API Key"
            placeholder = "sk-..."
        elif provider_id == "anthropic":
            current_api_key = settings.get_setting("api", "anthropic_api_key", "")
            prompt_text = "Enter your Anthropic API key:"
            window_title = "Anthropic API Key"
            placeholder = "sk-ant-..."
        elif provider_id == "google":
            current_api_key = settings.get_setting("api", "google_api_key", "")
            prompt_text = "Enter your Google API key:"
            window_title = "Google API Key"
            placeholder = "AIzaSy..."
        elif provider_id == "openrouter":
            current_api_key = settings.get_setting("api", "openrouter_api_key", "")
            prompt_text = "Enter your OpenRouter API key:"
            window_title = "OpenRouter API Key"
            placeholder = "sk-or-..."
        elif provider_id == "ollama":
            current_api_key = settings.get_setting("api", "ollama_host", "http://localhost:11434")
            prompt_text = "Enter your Ollama host URL:"
            window_title = "Ollama Host"
            placeholder = "http://localhost:11434"
        else:
            current_api_key = ""
            prompt_text = f"Enter your {provider_name} API key:"
            window_title = f"{provider_name} API Key"
            placeholder = ""
        
        # Show input dialog
        api_key, ok = QInputDialog.getText(
            self, 
            window_title, 
            prompt_text,
            echo=QLineEdit.EchoMode.Normal,
            text=current_api_key
        )
        
        if ok and api_key:
            # Set the correct setting based on provider
            if provider_id == "openai":
                settings.set_setting("api", "openai_api_key", api_key)
            elif provider_id == "anthropic":
                settings.set_setting("api", "anthropic_api_key", api_key)
            elif provider_id == "google":
                settings.set_setting("api", "google_api_key", api_key)
            elif provider_id == "openrouter":
                settings.set_setting("api", "openrouter_api_key", api_key)
            elif provider_id == "ollama":
                # Format Ollama host URL
                if not api_key.startswith("http"):
                    api_key = f"http://{api_key}"
                if api_key.endswith("/"):
                    api_key = api_key[:-1]
                settings.set_setting("api", "ollama_host", api_key)
            
            # Save settings
            settings.save_settings()
            
            # Get model
            model = self.model_combo.currentText().strip()
            if model:
                # Save model setting
                if provider_id == "openai":
                    settings.set_setting("api", "openai_model", model)
                elif provider_id == "anthropic":
                    settings.set_setting("api", "anthropic_model", model)
                elif provider_id == "google":
                    settings.set_setting("api", "google_model", model)
                elif provider_id == "openrouter":
                    settings.set_setting("api", "openrouter_model", model)
                elif provider_id == "ollama":
                    settings.set_setting("api", "ollama_model", model)
                
                # Save updated settings
                settings.save_settings()
            
            # Update API config
            self.api_config = self._get_api_config()
            
            # Log the change
            if provider_id == "ollama":
                logger.info(f"Updated Ollama host to: {api_key}")
            else:
                logger.info(f"Updated API key for {provider_name}")
                
            # Set as default provider
            settings.set_setting("ai", "provider", provider_id)
            settings.save_settings()
            
            QMessageBox.information(
                self, 
                "Settings Updated", 
                f"{provider_name} settings updated successfully."
            )

    def _on_temperature_changed(self):
        """Handle temperature change."""
        # Update temperature value label
        self.temperature_value.setText(f"{self.temperature_slider.value() / 100:.2f}")

    def closeEvent(self, event):
        """Clean up resources when the dialog is closed."""
        # Clean up worker thread if it exists
        try:
            if hasattr(self, 'summary_thread') and self.summary_thread is not None:
                if self.summary_thread.isRunning():
                    self.summary_thread.quit()
                    self.summary_thread.wait(1000)  # Wait up to 1 second
        except RuntimeError:
            # Handle case where thread might have been deleted
            logger.warning("Summary thread was already deleted during closeEvent")
        except Exception as e:
            logger.warning(f"Error cleaning up summary thread during closeEvent: {e}")
            
        # Clean up sections worker thread if it exists
        try:
            if hasattr(self, 'sections_thread') and self.sections_thread is not None:
                if self.sections_thread.isRunning():
                    self.sections_thread.quit()
                    self.sections_thread.wait(1000)  # Wait up to 1 second
        except RuntimeError:
            # Handle case where thread might have been deleted
            logger.warning("Sections thread was already deleted during closeEvent")
        except Exception as e:
            logger.warning(f"Error cleaning up sections thread during closeEvent: {e}")
            
        # Delete workers explicitly
        if hasattr(self, 'summary_worker') and self.summary_worker is not None:
            try:
                self.summary_worker.deleteLater()
            except Exception:
                pass
            self.summary_worker = None
            
        if hasattr(self, 'sections_worker') and self.sections_worker is not None:
            try:
                self.sections_worker.deleteLater()
            except Exception:
                pass
            self.sections_worker = None
            
        # Call parent's closeEvent
        super().closeEvent(event)
