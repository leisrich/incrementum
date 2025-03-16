def generate_qa_pairs(self, extract_id, max_pairs=5, ai_config=None):
    """
    Generate question-answer pairs from an extract using AI.

    Args:
        extract_id: Extract ID
        max_pairs: Maximum number of pairs to generate
        ai_config: Dictionary containing AI provider configuration
            {provider, api_key, model}
            
    Returns:
        List of LearningItem objects
    """
    # Get extract
    extract = self.db_session.query(Extract).get(extract_id)
    if not extract:
        logger.error(f"Extract not found: {extract_id}")
        return []
    
    content = extract.content
    
    # For short content, just use rule-based approach
    if len(content.split()) < 30:
        return self._generate_template_qa(extract, max_pairs)
    
    # If we have AI configuration, use it
    if ai_config and ai_config.get('api_key'):
        try:
            qa_pairs = self._generate_ai_qa_pairs(content, max_pairs, ai_config)
            if qa_pairs:
                return self._create_learning_items_from_qa(extract, qa_pairs)
        except Exception as e:
            logger.exception(f"Error generating QA pairs with AI: {e}")
            # Fall back to template-based generation
    
    # If AI failed or not available, use template-based approach
    return self._generate_template_qa(extract, max_pairs)

def generate_cloze_deletions(self, extract_id, max_items=5, ai_config=None):
    """
    Generate cloze deletion items from an extract.

    Args:
        extract_id: Extract ID
        max_items: Maximum number of items to generate
        ai_config: Dictionary containing AI provider configuration
            {provider, api_key, model}
            
    Returns:
        List of LearningItem objects
    """
    # Get extract
    extract = self.db_session.query(Extract).get(extract_id)
    if not extract:
        logger.error(f"Extract not found: {extract_id}")
        return []
    
    content = extract.content
    
    # For short content, just use rule-based approach
    if len(content.split()) < 30:
        return self._generate_template_cloze(extract, max_items)
    
    # If we have AI configuration, use it
    if ai_config and ai_config.get('api_key'):
        try:
            cloze_items = self._generate_ai_cloze_items(content, max_items, ai_config)
            if cloze_items:
                return self._create_learning_items_from_cloze(extract, cloze_items)
        except Exception as e:
            logger.exception(f"Error generating cloze items with AI: {e}")
            # Fall back to template-based generation
    
    # If AI failed or not available, use template-based approach
    return self._generate_template_cloze(extract, max_items)

def _generate_ai_qa_pairs(self, content, max_pairs, ai_config):
    """
    Generate QA pairs using AI.
    
    Args:
        content: Extract content
        max_pairs: Maximum number of pairs to generate
        ai_config: AI provider configuration
        
    Returns:
        List of dictionaries with questions and answers
    """
    provider = ai_config.get('provider', 'openai')
    api_key = ai_config.get('api_key')
    model = ai_config.get('model')
    
    from core.document_processor.summarizer import AI_PROVIDERS
    
    if provider not in AI_PROVIDERS:
        logger.error(f"Unknown AI provider: {provider}")
        return []
        
    prompt = f"""
    Generate {max_pairs} high-quality question-answer pairs based on the following text. 
    The questions should test understanding of key concepts and information.
    Make the questions specific and precise.
    Format your response as a JSON array of objects with 'question' and 'answer' fields.
    
    Text: {content}
    """
    
    try:
        if provider == 'openai':
            return self._generate_openai_qa(prompt, api_key, model, max_pairs)
        elif provider == 'anthropic':
            return self._generate_anthropic_qa(prompt, api_key, model, max_pairs)
        elif provider == 'openrouter':
            return self._generate_openrouter_qa(prompt, api_key, model, max_pairs)
        elif provider == 'google':
            return self._generate_google_qa(prompt, api_key, model, max_pairs)
        else:
            return []
    except Exception as e:
        logger.exception(f"Error generating QA pairs with AI provider {provider}: {e}")
        return []

def _generate_ai_cloze_items(self, content, max_items, ai_config):
    """
    Generate cloze deletion items using AI.
    
    Args:
        content: Extract content
        max_items: Maximum number of items to generate
        ai_config: AI provider configuration
        
    Returns:
        List of dictionaries with cloze sentences and answers
    """
    provider = ai_config.get('provider', 'openai')
    api_key = ai_config.get('api_key')
    model = ai_config.get('model')
    
    from core.document_processor.summarizer import AI_PROVIDERS
    
    if provider not in AI_PROVIDERS:
        logger.error(f"Unknown AI provider: {provider}")
        return []
        
    prompt = f"""
    Generate {max_items} cloze deletion items based on the following text.
    For each item, select an important sentence and identify a key term to remove.
    Format your response as a JSON array of objects with 'sentence' and 'answer' fields.
    The 'sentence' should have the key term replaced with [...], and 'answer' should be the removed term.
    
    Text: {content}
    """
    
    try:
        if provider == 'openai':
            return self._generate_openai_cloze(prompt, api_key, model, max_items)
        elif provider == 'anthropic':
            return self._generate_anthropic_cloze(prompt, api_key, model, max_items)
        elif provider == 'openrouter':
            return self._generate_openrouter_cloze(prompt, api_key, model, max_items)
        elif provider == 'google':
            return self._generate_google_cloze(prompt, api_key, model, max_items)
        else:
            return []
    except Exception as e:
        logger.exception(f"Error generating cloze items with AI provider {provider}: {e}")
        return []

def _generate_openai_qa(self, prompt, api_key, model, max_pairs):
    """Generate QA pairs using OpenAI."""
    import requests
    import json
    
    from core.document_processor.summarizer import AI_PROVIDERS
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": model or "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that generates high-quality question-answer pairs for learning."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    response = requests.post(
        AI_PROVIDERS['openai']['endpoint'],
        headers=headers,
        json=data,
        timeout=30
    )
    
    if response.status_code == 200:
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        try:
            # Extract JSON from response
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                
            qa_pairs = json.loads(json_str)
            
            # Ensure we have proper format
            validated_pairs = []
            for pair in qa_pairs:
                if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                    validated_pairs.append(pair)
            
            return validated_pairs
        except Exception as e:
            logger.exception(f"Error parsing OpenAI response: {e}")
            return []
    else:
        logger.error(f"OpenAI API request failed: {response.status_code} - {response.text}")
        return []

def _generate_anthropic_qa(self, prompt, api_key, model, max_pairs):
    """Generate QA pairs using Anthropic Claude."""
    import requests
    import json
    
    from core.document_processor.summarizer import AI_PROVIDERS
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    
    data = {
        "model": model or "claude-3-haiku-20240307",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    response = requests.post(
        AI_PROVIDERS['anthropic']['endpoint'],
        headers=headers,
        json=data,
        timeout=30
    )
    
    if response.status_code == 200:
        result = response.json()
        content = result["content"][0]["text"]
        
        try:
            # Extract JSON from response
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                
            qa_pairs = json.loads(json_str)
            
            # Ensure we have proper format
            validated_pairs = []
            for pair in qa_pairs:
                if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                    validated_pairs.append(pair)
            
            return validated_pairs
        except Exception as e:
            logger.exception(f"Error parsing Anthropic response: {e}")
            return []
    else:
        logger.error(f"Anthropic API request failed: {response.status_code} - {response.text}")
        return []

def _generate_openrouter_qa(self, prompt, api_key, model, max_pairs):
    """Generate QA pairs using OpenRouter."""
    import requests
    import json
    
    from core.document_processor.summarizer import AI_PROVIDERS
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://incrementum.app"  # Replace with your app domain
    }
    
    data = {
        "model": model or "openai/gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that generates high-quality question-answer pairs for learning."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3
    }
    
    response = requests.post(
        AI_PROVIDERS['openrouter']['endpoint'],
        headers=headers,
        json=data,
        timeout=30
    )
    
    if response.status_code == 200:
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        try:
            # Extract JSON from response
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                
            qa_pairs = json.loads(json_str)
            
            # Ensure we have proper format
            validated_pairs = []
            for pair in qa_pairs:
                if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                    validated_pairs.append(pair)
            
            return validated_pairs
        except Exception as e:
            logger.exception(f"Error parsing OpenRouter response: {e}")
            return []
    else:
        logger.error(f"OpenRouter API request failed: {response.status_code} - {response.text}")
        return []

def _generate_google_qa(self, prompt, api_key, model, max_pairs):
    """Generate QA pairs using Google Gemini."""
    import requests
    import json
    
    from core.document_processor.summarizer import AI_PROVIDERS
    
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.3
        }
    }
    
    endpoint = f"{AI_PROVIDERS['google']['endpoint']}?key={api_key}"
    response = requests.post(
        endpoint,
        headers=headers,
        json=data,
        timeout=30
    )
    
    if response.status_code == 200:
        result = response.json()
        content = result["candidates"][0]["content"]["parts"][0]["text"]
        
        try:
            # Extract JSON from response
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()
                
            qa_pairs = json.loads(json_str)
            
            # Ensure we have proper format
            validated_pairs = []
            for pair in qa_pairs:
                if isinstance(pair, dict) and 'question' in pair and 'answer' in pair:
                    validated_pairs.append(pair)
            
            return validated_pairs
        except Exception as e:
            logger.exception(f"Error parsing Google response: {e}")
            return []
    else:
        logger.error(f"Google API request failed: {response.status_code} - {response.text}")
        return []

# The methods for generating cloze items are very similar to the QA methods
def _generate_openai_cloze(self, prompt, api_key, model, max_items):
    """Similar implementation to _generate_openai_qa but for cloze items"""
    # Implementation similar to _generate_openai_qa but for cloze items
    return self._generate_openai_qa(prompt, api_key, model, max_items)  # Reuse the same method as structure is identical

def _generate_anthropic_cloze(self, prompt, api_key, model, max_items):
    """Similar implementation to _generate_anthropic_qa but for cloze items"""
    return self._generate_anthropic_qa(prompt, api_key, model, max_items)

def _generate_openrouter_cloze(self, prompt, api_key, model, max_items):
    """Similar implementation to _generate_openrouter_qa but for cloze items"""
    return self._generate_openrouter_qa(prompt, api_key, model, max_items)

def _generate_google_cloze(self, prompt, api_key, model, max_items):
    """Similar implementation to _generate_google_qa but for cloze items"""
    return self._generate_google_qa(prompt, api_key, model, max_items)

def _create_learning_items_from_qa(self, extract, qa_pairs):
    """
    Create learning items from generated QA pairs.
    
    Args:
        extract: Extract object
        qa_pairs: List of dictionaries with questions and answers
        
    Returns:
        List of LearningItem objects
    """
    from datetime import datetime
    
    items = []
    
    for pair in qa_pairs:
        item = LearningItem(
            extract_id=extract.id,
            item_type='qa',
            question=pair['question'],
            answer=pair['answer'],
            priority=extract.priority,
            created_date=datetime.utcnow()
        )
        
        items.append(item)
    
    return items

def _create_learning_items_from_cloze(self, extract, cloze_items):
    """
    Create learning items from generated cloze items.
    
    Args:
        extract: Extract object
        cloze_items: List of dictionaries with sentences and answers
        
    Returns:
        List of LearningItem objects
    """
    from datetime import datetime
    
    items = []
    
    for item in cloze_items:
        if 'sentence' in item and 'answer' in item:
            learning_item = LearningItem(
                extract_id=extract.id,
                item_type='cloze',
                question=item['sentence'],
                answer=item['answer'],
                priority=extract.priority,
                created_date=datetime.utcnow()
            )
            
            items.append(learning_item)
    
    return items 