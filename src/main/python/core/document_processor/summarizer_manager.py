#!/usr/bin/env python3
# core/document_processor/summarizer_manager.py

import logging
from typing import Dict, Any, List, Optional

from core.document_processor.summarizer import DocumentSummarizer, AI_PROVIDERS
from core.utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)

class SummarizerManager:
    """Manager for document summarization operations."""
    
    def __init__(self, db_session):
        """Initialize the summarizer manager.
        
        Args:
            db_session: Database session
        """
        self.db_session = db_session
        
        # Get API configuration from settings
        self.api_config = self._get_api_config()
        
        # Create document summarizer
        self.summarizer = DocumentSummarizer(db_session, self.api_config)
    
    def get_available_providers(self) -> List[str]:
        """Get a list of available AI providers.
        
        Returns:
            List of provider display names
        """
        return [provider_info["name"] for _, provider_info in AI_PROVIDERS.items()]
    
    def get_provider_id(self, provider_name: str) -> Optional[str]:
        """Get provider ID from display name.
        
        Args:
            provider_name: Provider display name
            
        Returns:
            Provider ID or None if not found
        """
        for provider_id, provider_info in AI_PROVIDERS.items():
            if provider_info["name"] == provider_name:
                return provider_id
        return None
    
    def get_provider_models(self, provider_name: str) -> List[str]:
        """Get available models for a provider.
        
        Args:
            provider_name: Provider display name
            
        Returns:
            List of model names
        """
        provider_id = self.get_provider_id(provider_name)
        if provider_id and provider_id in AI_PROVIDERS:
            return AI_PROVIDERS[provider_id].get("models", [])
        return []
    
    def summarize_document(self, document_id: int, level: str = 'medium', 
                         use_ai: bool = True) -> Dict[str, Any]:
        """Summarize a document.
        
        Args:
            document_id: Document ID
            level: Summary level ('brief', 'medium', 'detailed')
            use_ai: Whether to use AI for summarization
            
        Returns:
            Dictionary with summary information
        """
        return self.summarizer.summarize_document(document_id, level, use_ai)
    
    def extract_key_sections(self, document_id: int, max_sections: int = 5) -> List[Dict[str, Any]]:
        """Extract key sections from a document.
        
        Args:
            document_id: Document ID
            max_sections: Maximum number of sections to extract
            
        Returns:
            List of dictionaries with section information
        """
        return self.summarizer.extract_key_sections(document_id, max_sections)
    
    def create_summary_extract(self, document_id: int, level: str = 'medium',
                             use_ai: bool = True) -> Optional[int]:
        """Create an extract with document summary.
        
        Args:
            document_id: Document ID
            level: Summary level ('brief', 'medium', 'detailed')
            use_ai: Whether to use AI for summarization
            
        Returns:
            Extract ID if successful, None otherwise
        """
        return self.summarizer.create_summary_extract(document_id, level, use_ai)
    
    def _get_api_config(self) -> Dict[str, Any]:
        """Get API configuration from settings.
        
        Returns:
            API configuration dictionary
        """
        try:
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
            else:
                # For other providers, get the API key normally
                api_key = settings.get_setting("api", setting_key, "")
                
                # Get model for the provider
                model_setting_key = f"{provider}_model"
                available_models = AI_PROVIDERS[provider].get("models", [])
                model = settings.get_setting("api", model_setting_key, available_models[0] if available_models else "")
            
            # Build config dictionary
            return {
                "provider": provider,
                "api_key": api_key,
                "model": model
            }
            
        except Exception as e:
            logger.exception(f"Error getting API configuration: {e}")
            return {}
    
    def update_api_config(self, provider: str, api_key: str, model: str) -> None:
        """Update the API configuration.
        
        Args:
            provider: Provider ID
            api_key: API key or host URL
            model: Model name
        """
        self.api_config = {
            "provider": provider,
            "api_key": api_key,
            "model": model
        }
        self.summarizer.api_config = self.api_config 