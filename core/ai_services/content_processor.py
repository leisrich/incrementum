# core/ai_services/content_processor.py

import logging
from typing import Dict, Any, Optional

from core.ai_services.llm_service import LLMService

logger = logging.getLogger(__name__)

class ContentProcessor:
    """Processes content using LLM services to generate summaries and analyses."""
    
    def __init__(self, llm_service: LLMService):
        """Initialize with an LLM service."""
        self.llm_service = llm_service
    
    def generate_summary(self, content: str, max_length: int = 500, 
                         focus_areas: Optional[str] = None) -> str:
        """
        Generate a summary of the content.
        
        Args:
            content: The content to summarize
            max_length: Maximum length of the summary in words
            focus_areas: Optional areas to focus on in the summary
            
        Returns:
            Generated summary
        """
        if not self.llm_service.is_configured():
            return "LLM service is not properly configured. Please check API settings."
        
        # Build the prompt
        prompt = f"Please summarize the following content in about {max_length} words:\n\n{content}"
        
        if focus_areas:
            prompt += f"\n\nPlease focus on these aspects: {focus_areas}"
        
        # Generate summary
        try:
            return self.llm_service.generate_text(prompt, max_tokens=max_length * 5)
        except Exception as e:
            logger.exception(f"Error generating summary: {e}")
            return f"Error generating summary: {str(e)}"
    
    def generate_article(self, content: str, style: str = "informative", 
                        length: str = "medium", tone: str = "neutral") -> str:
        """
        Generate a full article based on content.
        
        Args:
            content: The source content
            style: Article style (informative, analytical, conversational)
            length: Article length (short, medium, long)
            tone: Article tone (neutral, formal, casual)
            
        Returns:
            Generated article
        """
        if not self.llm_service.is_configured():
            return "LLM service is not properly configured. Please check API settings."
        
        # Map length to approximate word count
        length_map = {
            "short": 300,
            "medium": 800,
            "long": 1500
        }
        word_count = length_map.get(length.lower(), 800)
        
        # Build the prompt
        prompt = (
            f"Based on the following content, generate a {length} article "
            f"(approximately {word_count} words) in a {style} style with a {tone} tone.\n\n"
            f"Content:\n{content}"
        )
        
        # Generate article
        try:
            return self.llm_service.generate_text(prompt, max_tokens=word_count * 5, temperature=0.7)
        except Exception as e:
            logger.exception(f"Error generating article: {e}")
            return f"Error generating article: {str(e)}"
    
    def extract_key_points(self, content: str, num_points: int = 5) -> str:
        """
        Extract key points from content.
        
        Args:
            content: The content to analyze
            num_points: Number of key points to extract
            
        Returns:
            Formatted key points
        """
        if not self.llm_service.is_configured():
            return "LLM service is not properly configured. Please check API settings."
        
        # Build the prompt
        prompt = f"Extract the {num_points} most important points from the following content:\n\n{content}"
        
        # Generate key points
        try:
            return self.llm_service.generate_text(prompt, max_tokens=num_points * 100, temperature=0.3)
        except Exception as e:
            logger.exception(f"Error extracting key points: {e}")
            return f"Error extracting key points: {str(e)}"
    
    def answer_questions(self, content: str, questions: str) -> str:
        """
        Answer specific questions based on content.
        
        Args:
            content: The content to analyze
            questions: The questions to answer
            
        Returns:
            Answers to the questions
        """
        if not self.llm_service.is_configured():
            return "LLM service is not properly configured. Please check API settings."
        
        # Build the prompt
        prompt = (
            f"Based on the following content, please answer these questions:\n\n"
            f"Content:\n{content}\n\n"
            f"Questions:\n{questions}"
        )
        
        # Generate answers
        try:
            return self.llm_service.generate_text(prompt, max_tokens=1500, temperature=0.4)
        except Exception as e:
            logger.exception(f"Error answering questions: {e}")
            return f"Error answering questions: {str(e)}" 