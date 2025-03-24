# core/ai_services/llm_service.py

import os
import logging
import requests
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)

class LLMService(ABC):
    """Base class for LLM service integrations."""
    
    @abstractmethod
    def generate_text(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Generate text based on a prompt."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if the service is properly configured with API keys."""
        pass

class OpenAIService(LLMService):
    """OpenAI API integration."""
    
    def __init__(self, api_key: str = None, model: str = "gpt-3.5-turbo"):
        self.api_key = api_key
        self.model = model
        
    def generate_text(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Generate text using OpenAI API."""
        if not self.api_key:
            logger.error("OpenAI API key not set")
            return "Error: OpenAI API key not set"
        
        try:
            import openai
            client = openai.OpenAI(api_key=self.api_key)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that summarizes content."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return response.choices[0].message.content.strip()
            
        except ImportError:
            return "Error: OpenAI Python package not installed"
        except Exception as e:
            logger.exception(f"Error generating text with OpenAI: {e}")
            return f"Error generating text: {str(e)}"
    
    def is_configured(self) -> bool:
        """Check if the OpenAI API key is set."""
        return bool(self.api_key)

class GeminiService(LLMService):
    """Google Gemini API integration."""
    
    def __init__(self, api_key: str = None, model: str = "gemini-1.5-pro"):
        self.api_key = api_key
        self.model = model
    
    def generate_text(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Generate text using Google Gemini API."""
        try:
            # Import here to prevent dependency requirement when not using this service
            import google.generativeai as genai
        except ImportError:
            logger.error("Google GenerativeAI Python package not installed")
            return "Error: Google GenerativeAI Python package not installed."

        if not self.api_key:
            logger.error("Gemini API key not set")
            return "Error: Gemini API key not set"

        try:
            # Configure the Gemini API
            genai.configure(api_key=self.api_key)
            
            # Map model names to appropriate Gemini API model identifiers
            model_mapping = {
                "gemini-2.0-pro": "gemini-2.0-pro",
                "gemini-2.0-flash": "gemini-2.0-flash",
                "gemini-2.0-flash-lite": "gemini-2.0-flash-lite",
                "gemini-1.5-pro": "gemini-1.5-pro",
                "gemini-1.5-flash": "gemini-1.5-flash"
            }
            
            # Use the mapped model name or default to the original name
            model_name = model_mapping.get(self.model, self.model)
            
            # For older models that might not have the prefix
            if not model_name.startswith("models/"):
                model_name = f"models/{model_name}"
                
            # Get the model
            model = genai.GenerativeModel(model_name)
            
            # Generate content
            generation_config = {
                "temperature": temperature,
            }
            if max_tokens:
                generation_config["max_output_tokens"] = max_tokens
                
            response = model.generate_content(
                prompt,
                generation_config=generation_config
            )
            
            # Extract the text from the response
            if hasattr(response, 'text'):
                return response.text.strip()
            else:
                # Handle different response formats
                return str(response)
                
        except Exception as e:
            logger.exception(f"Error generating text with Gemini: {e}")
            return f"Error generating text: {str(e)}"
    
    def is_configured(self) -> bool:
        """Check if the Gemini API key is set."""
        return bool(self.api_key)

class ClaudeService(LLMService):
    """Service for interacting with Anthropic Claude API."""

    def __init__(self, api_key=None, model="claude-3-5-sonnet-20241022"):
        self.api_key = api_key
        self.model = model

    def generate_text(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Generate text using Claude API."""
        if not self.api_key:
            logger.error("Claude API key not set")
            return "Error: Claude API key not set"

        try:
            # Check for Anthropic library
            import anthropic
        except ImportError:
            logger.error("Anthropic Python package not installed")
            return "Error: Anthropic Python package not installed. Run 'pip install anthropic'"

        try:
            client = anthropic.Anthropic(api_key=self.api_key)
            
            # Handle model validation
            valid_models = [
                "claude-3-7-sonnet-20250219",
                "claude-3-5-sonnet-20241022",
                "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229",
                "claude-3-sonnet-20240229",
                "claude-3-haiku-20240307",
                "claude-2.0",
                "claude-2"
            ]
            
            if self.model not in valid_models:
                logger.warning(f"Unknown Claude model: {self.model}, using claude-3-5-sonnet-20241022 instead")
                model = "claude-3-5-sonnet-20241022"
            else:
                model = self.model
            
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return message.content[0].text

        except Exception as e:
            logger.exception(f"Error generating text with Claude: {e}")
            return f"Error generating text: {str(e)}"
    
    def is_configured(self) -> bool:
        """Check if the Claude API key is set."""
        return bool(self.api_key)

class OpenRouterService(LLMService):
    """OpenRouter API integration."""
    
    def __init__(self, api_key: str = None, model: str = "openai/gpt-3.5-turbo"):
        self.api_key = api_key
        self.model = model
    
    def generate_text(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Generate text using OpenRouter API."""
        if not self.api_key:
            logger.error("OpenRouter API key not set")
            return "Error: OpenRouter API key not set"
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that summarizes content."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=data
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result["choices"][0]["message"]["content"].strip()
            
        except Exception as e:
            logger.exception(f"Error generating text with OpenRouter: {e}")
            return f"Error generating text: {str(e)}"
    
    def is_configured(self) -> bool:
        """Check if the OpenRouter API key is set."""
        return bool(self.api_key)

class OllamaService(LLMService):
    """Ollama local LLM integration."""
    
    def __init__(self, host: str = "http://localhost:11434", model: str = "llama3"):
        self.host = host
        self.model = model
    
    def generate_text(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Generate text using Ollama API."""
        try:
            url = f"{self.host}/api/generate"
            
            data = {
                "model": self.model,
                "prompt": prompt,
                "system": "You are a helpful assistant that summarizes content.",
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                }
            }
            
            response = requests.post(url, json=data)
            response.raise_for_status()
            
            # Ollama streams responses, so we need to collect the full response
            result = ""
            for line in response.iter_lines():
                if line:
                    response_json = json.loads(line)
                    if "response" in response_json:
                        result += response_json["response"]
                    
                    # Break if we're done
                    if response_json.get("done", False):
                        break
            
            return result.strip()
            
        except Exception as e:
            logger.exception(f"Error generating text with Ollama: {e}")
            return f"Error generating text: {str(e)}"
    
    def is_configured(self) -> bool:
        """Check if Ollama is running by making a simple request."""
        try:
            response = requests.get(f"{self.host}/api/version")
            return response.status_code == 200
        except:
            return False

class LLMServiceFactory:
    """Factory for creating LLM service instances."""
    
    @staticmethod
    def create_service(service_type: str, settings_manager) -> LLMService:
        """Create an LLM service based on the service type."""
        if service_type == "openai":
            api_key = settings_manager.get_setting("api", "openai_api_key", "")
            model = settings_manager.get_setting("api", "openai_model", "gpt-4o")
            return OpenAIService(api_key, model)
        
        elif service_type == "gemini":
            api_key = settings_manager.get_setting("api", "gemini_api_key", "")
            model = settings_manager.get_setting("api", "gemini_model", "gemini-1.5-pro")
            return GeminiService(api_key, model)
        
        elif service_type == "claude":
            api_key = settings_manager.get_setting("api", "claude_api_key", "")
            model = settings_manager.get_setting("api", "claude_model", "claude-3-5-sonnet-20241022")
            return ClaudeService(api_key, model)
        
        elif service_type == "openrouter":
            api_key = settings_manager.get_setting("api", "openrouter_api_key", "")
            model = settings_manager.get_setting("api", "openrouter_model", "openai/gpt-3.5-turbo")
            return OpenRouterService(api_key, model)
        
        elif service_type == "ollama":
            host = settings_manager.get_setting("api", "ollama_host", "http://localhost:11434")
            model = settings_manager.get_setting("api", "ollama_model", "llama3")
            return OllamaService(host, model)
        
        else:
            logger.error(f"Unknown service type: {service_type}")
            return None 
