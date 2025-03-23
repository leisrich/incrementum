# core/content_extractor/nlp_extractor.py

import logging
import re
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime

import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tag import pos_tag
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

from sqlalchemy.orm import Session
from core.knowledge_base.models import Document, Extract, LearningItem

logger = logging.getLogger(__name__)

class NLPExtractor:
    """
    Enhanced knowledge extractor using NLP techniques to identify 
    important content and generate better learning items.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        
        # Initialize NLTK resources
        try:
            nltk.data.find('tokenizers/punkt')
            nltk.data.find('taggers/averaged_perceptron_tagger')
            nltk.data.find('corpora/stopwords')
            nltk.data.find('corpora/wordnet')
        except LookupError:
            nltk.download('punkt')
            nltk.download('averaged_perceptron_tagger')
            nltk.download('stopwords')
            nltk.download('wordnet')
        
        self.stop_words = set(stopwords.words('english'))
        self.lemmatizer = WordNetLemmatizer()
        
        # Initialize spaCy model (lightweight English model)
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            # If model is not installed, download it
            spacy.cli.download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")
    
    def identify_key_concepts(self, text: str, num_concepts: int = 5) -> List[Dict[str, Any]]:
        """
        Identify key concepts in a text using NLP techniques.
        
        Args:
            text: The text to analyze
            num_concepts: Number of key concepts to extract
            
        Returns:
            List of dictionaries with key concepts information
        """
        # Process text with spaCy
        doc = self.nlp(text)
        
        # Extract named entities
        entities = []
        for ent in doc.ents:
            entities.append({
                'text': ent.text,
                'type': ent.label_,
                'start': ent.start_char,
                'end': ent.end_char,
                'importance': 0.8  # Higher importance for named entities
            })
        
        # Extract noun phrases
        noun_phrases = []
        for chunk in doc.noun_chunks:
            # Skip if it's just a pronoun or determiner
            if chunk.root.pos_ in ['PRON', 'DET']:
                continue
                
            # Skip if it's very short (just one word and not a proper noun)
            if len(chunk.text.split()) == 1 and chunk.root.pos_ != 'PROPN':
                continue
                
            noun_phrases.append({
                'text': chunk.text,
                'type': 'NOUN_PHRASE',
                'start': chunk.start_char,
                'end': chunk.end_char,
                'importance': 0.6  # Medium importance
            })
        
        # Extract important words using TF-IDF
        sentences = [sent.text for sent in doc.sents]
        if len(sentences) < 2:
            # Not enough sentences for meaningful TF-IDF
            # Add original text as a backup
            sentences = [text]
        
        try:
            # Calculate TF-IDF
            vectorizer = TfidfVectorizer(
                max_features=50,
                stop_words='english',
                ngram_range=(1, 2)  # Include single words and bigrams
            )
            tfidf_matrix = vectorizer.fit_transform(sentences)
            
            # Get top-scoring terms
            feature_names = vectorizer.get_feature_names_out()
            
            important_terms = []
            # For each sentence, get its highest TF-IDF terms
            for i, sentence in enumerate(sentences):
                if tfidf_matrix.shape[0] <= i:
                    continue  # Skip if matrix doesn't have enough rows
                    
                # Get top terms in this sentence
                feature_index = tfidf_matrix[i, :].nonzero()[1]
                tfidf_scores = zip(feature_index, [tfidf_matrix[i, x] for x in feature_index])
                
                # Sort by score
                sorted_terms = sorted(tfidf_scores, key=lambda x: x[1], reverse=True)
                
                # Add top terms
                for idx, score in sorted_terms[:3]:  # Top 3 terms per sentence
                    term = feature_names[idx]
                    
                    # Find position in original text
                    term_pos = text.find(term)
                    if term_pos >= 0:
                        important_terms.append({
                            'text': term,
                            'type': 'TFIDF_TERM',
                            'start': term_pos,
                            'end': term_pos + len(term),
                            'importance': 0.5 + (score * 0.5)  # Scale importance by TF-IDF score
                        })
        
        except Exception as e:
            logger.warning(f"Error calculating TF-IDF: {e}")
            # If TF-IDF fails, add empty list
            important_terms = []
        
        # Combine all concepts
        all_concepts = entities + noun_phrases + important_terms
        
        # Remove duplicates (by text)
        seen_texts = set()
        unique_concepts = []
        
        for concept in all_concepts:
            if concept['text'].lower() not in seen_texts:
                seen_texts.add(concept['text'].lower())
                unique_concepts.append(concept)
        
        # Sort by importance and return top N
        sorted_concepts = sorted(unique_concepts, key=lambda x: x['importance'], reverse=True)
        
        return sorted_concepts[:num_concepts]
    
    def segment_document(self, document_id: int) -> List[Dict[str, Any]]:
        """
        Segment a document into meaningful sections using NLP.
        
        Args:
            document_id: ID of the document to segment
            
        Returns:
            List of segment dictionaries
        """
        document = self.db_session.query(Document).get(document_id)
        if not document:
            logger.error(f"Document not found: {document_id}")
            return []
        
        # Get document content
        content = self._get_document_content(document)
        if not content:
            return []
        
        # Process with spaCy
        doc = self.nlp(content)
        
        # Split into sentences
        sentences = list(doc.sents)
        if not sentences:
            return []
        
        # Group sentences into paragraphs
        paragraphs = self._group_sentences_into_paragraphs(sentences)
        
        # Identify section headers
        sections = self._identify_sections(paragraphs)
        
        # Score sections for importance
        scored_sections = self._score_sections_for_importance(sections)
        
        return scored_sections
    
    def _get_document_content(self, document: Document) -> str:
        """Get the full text content of a document."""
        try:
            if document.content_type == 'pdf':
                from pdfminer.high_level import extract_text
                return extract_text(document.file_path)
            
            elif document.content_type in ['html', 'htm']:
                from bs4 import BeautifulSoup
                with open(document.file_path, 'r', encoding='utf-8') as f:
                    soup = BeautifulSoup(f.read(), 'lxml')
                    return soup.get_text(separator='\n')
            
            else:  # Plain text
                with open(document.file_path, 'r', encoding='utf-8') as f:
                    return f.read()
                    
        except Exception as e:
            logger.exception(f"Error reading document content: {e}")
            return ""
    
    def _group_sentences_into_paragraphs(self, sentences: List) -> List[Dict[str, Any]]:
        """Group sentences into paragraphs based on text layout."""
        paragraphs = []
        current_paragraph = []
        
        for i, sentence in enumerate(sentences):
            text = sentence.text.strip()
            if not text:
                continue
                
            # Add sentence to current paragraph
            current_paragraph.append(text)
            
            # Check if end of paragraph
            # This is a simple heuristic - in a real system, you would use
            # layout information from the document
            if text.endswith('.') or text.endswith('!') or text.endswith('?'):
                # If next sentence starts with a capital letter and is after a line break,
                # or this is the last sentence, end the paragraph
                if (i == len(sentences) - 1 or 
                    (i < len(sentences) - 1 and
                     sentences[i+1].text.strip() and
                     sentences[i+1].text.strip()[0].isupper() and
                     sentence.end_char < sentences[i+1].start_char - 1)):
                    
                    # Add paragraph
                    if current_paragraph:
                        paragraph_text = ' '.join(current_paragraph)
                        paragraphs.append({
                            'type': 'paragraph',
                            'content': paragraph_text,
                            'sentences': current_paragraph
                        })
                        current_paragraph = []
        
        # Add any remaining sentences
        if current_paragraph:
            paragraph_text = ' '.join(current_paragraph)
            paragraphs.append({
                'type': 'paragraph',
                'content': paragraph_text,
                'sentences': current_paragraph
            })
        
        return paragraphs
    
    def _identify_sections(self, paragraphs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify section headers and group content into sections."""
        sections = []
        current_section = None
        
        for paragraph in paragraphs:
            content = paragraph['content']
            
            # Check if this paragraph looks like a header
            is_header = self._is_header(content)
            
            if is_header:
                # If we have a current section, add it to sections
                if current_section:
                    sections.append(current_section)
                
                # Start a new section
                current_section = {
                    'type': 'section',
                    'title': content,
                    'content': content,
                    'paragraphs': []
                }
            elif current_section:
                # Add to current section
                current_section['paragraphs'].append(paragraph)
                current_section['content'] += '\n\n' + content
            else:
                # No section yet, create a default one
                current_section = {
                    'type': 'section',
                    'title': 'Introduction',
                    'content': content,
                    'paragraphs': [paragraph]
                }
        
        # Add the last section
        if current_section:
            sections.append(current_section)
        
        return sections
    
    def _is_header(self, text: str) -> bool:
        """
        Check if a text is likely to be a header.
        
        This is a simple heuristic and could be improved with machine learning
        in a real system.
        """
        # If text is all uppercase, it's likely a header
        if text.isupper() and len(text) < 100:
            return True
        
        # If text is short and ends without punctuation, it might be a header
        if (len(text) < 100 and
            not text.endswith('.') and
            not text.endswith('!') and
            not text.endswith('?') and
            len(text.split()) < 10):
            return True
        
        # If text starts with a number followed by a dot (like "1. Introduction")
        if re.match(r'^\d+\.\s+\w+', text) and len(text) < 100:
            return True
        
        return False
    
    def _score_sections_for_importance(self, sections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score sections for importance based on content analysis."""
        result = []
        
        for section in sections:
            # Get key concepts
            concepts = self.identify_key_concepts(section['content'], num_concepts=3)
            
            # Calculate base priority (1-100 scale)
            # Headers get higher priority
            if section['type'] == 'section':
                base_priority = 70
            else:
                base_priority = 50
            
            # Adjust priority based on concepts
            # More important concepts increase priority
            concept_importance = sum(c['importance'] for c in concepts) / max(1, len(concepts))
            priority = min(100, int(base_priority + (concept_importance * 20)))
            
            # Add to result with priority and concepts
            result.append({
                'type': section['type'],
                'title': section.get('title', ''),
                'content': section['content'],
                'priority': priority,
                'key_concepts': concepts
            })
        
        return result
    
    def generate_qa_pairs(self, extract_id: int, max_pairs: int = 5) -> List[LearningItem]:
        """
        Generate question-answer pairs from an extract using NLP.
        
        Args:
            extract_id: ID of the extract
            max_pairs: Maximum number of pairs to generate
            
        Returns:
            List of LearningItem objects
        """
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            logger.error(f"Extract not found: {extract_id}")
            return []
        
        # Process text with spaCy
        doc = self.nlp(extract.content)
        
        qa_pairs = []
        
        # Generate factoid questions from named entities
        entity_pairs = self._generate_entity_questions(doc)
        qa_pairs.extend(entity_pairs[:max_pairs//2])
        
        # Generate questions from key sentences
        sentence_pairs = self._generate_sentence_questions(doc)
        qa_pairs.extend(sentence_pairs[:max_pairs - len(qa_pairs)])
        
        # Create learning items
        learning_items = []
        
        for pair in qa_pairs:
            item = LearningItem(
                extract_id=extract_id,
                item_type='qa',
                question=pair['question'],
                answer=pair['answer'],
                priority=extract.priority,
                created_date=datetime.utcnow()
            )
            
            self.db_session.add(item)
            learning_items.append(item)
        
        self.db_session.commit()
        return learning_items
    
    def _generate_entity_questions(self, doc) -> List[Dict[str, str]]:
        """Generate questions from named entities."""
        qa_pairs = []
        
        # Process entities
        for ent in doc.ents:
            # Skip very short entities
            if len(ent.text) < 3:
                continue
                
            if ent.label_ == 'PERSON':
                qa_pairs.append({
                    'question': f"Who is {ent.text} mentioned in the text?",
                    'answer': f"{ent.text} is mentioned in: '{self._get_entity_context(doc, ent)}'"
                })
            
            elif ent.label_ == 'ORG':
                qa_pairs.append({
                    'question': f"What is {ent.text} mentioned in the text?",
                    'answer': f"{ent.text} is mentioned in: '{self._get_entity_context(doc, ent)}'"
                })
            
            elif ent.label_ == 'GPE':  # Geopolitical entity
                qa_pairs.append({
                    'question': f"What is the significance of {ent.text} in this context?",
                    'answer': f"{ent.text} is mentioned in: '{self._get_entity_context(doc, ent)}'"
                })
            
            elif ent.label_ == 'DATE':
                qa_pairs.append({
                    'question': f"What happened on or during {ent.text}?",
                    'answer': f"On {ent.text}: '{self._get_entity_context(doc, ent)}'"
                })
            
            elif ent.label_ in ['CARDINAL', 'QUANTITY', 'PERCENT', 'MONEY']:
                qa_pairs.append({
                    'question': f"What is the significance of {ent.text} in this context?",
                    'answer': f"{ent.text} refers to: '{self._get_entity_context(doc, ent)}'"
                })
        
        return qa_pairs
    
    def _get_entity_context(self, doc, entity) -> str:
        """Get the sentence containing an entity."""
        for sent in doc.sents:
            if entity.start >= sent.start and entity.end <= sent.end:
                return sent.text
        return ""
    
    def _generate_sentence_questions(self, doc) -> List[Dict[str, str]]:
        """Generate questions from key sentences."""
        qa_pairs = []
        
        # Get sentences
        sentences = list(doc.sents)
        
        for sent in sentences:
            # Skip very short sentences
            if len(sent.text.split()) < 5:
                continue
                
            # Process sentence to generate questions
            for token in sent:
                # Find verbs to create questions
                if token.pos_ == 'VERB' and token.dep_ == 'ROOT':
                    # Get subject
                    subjects = [child for child in token.children if child.dep_ in ['nsubj', 'nsubjpass']]
                    
                    if subjects:
                        subject = subjects[0]
                        
                        # Create question
                        if token.lemma_ in ['be', 'have']:
                            # For "is" and "has" verbs
                            qa_pairs.append({
                                'question': f"What {token.text} {subject.text}?",
                                'answer': sent.text
                            })
                        else:
                            # For other verbs
                            qa_pairs.append({
                                'question': f"What does {subject.text} {token.lemma_}?",
                                'answer': sent.text
                            })
                    
                    # Try to get object for another question
                    objects = [child for child in token.children if child.dep_ in ['dobj', 'pobj']]
                    
                    if objects:
                        obj = objects[0]
                        
                        # Create question about the object
                        qa_pairs.append({
                            'question': f"What happens to the {obj.text} in this context?",
                            'answer': sent.text
                        })
        
        return qa_pairs
    
    def generate_cloze_deletions(self, extract_id: int, max_items: int = 5) -> List[LearningItem]:
        """
        Generate cloze deletion items from an extract using NLP.
        
        Args:
            extract_id: ID of the extract
            max_items: Maximum number of items to generate
            
        Returns:
            List of LearningItem objects
        """
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            logger.error(f"Extract not found: {extract_id}")
            return []
        
        # Process text with spaCy
        doc = self.nlp(extract.content)
        
        # Find key concepts
        key_concepts = self.identify_key_concepts(extract.content, num_concepts=max_items)
        
        # Create cloze deletions
        learning_items = []
        
        for concept in key_concepts:
            # Find the sentence containing this concept
            context = self._find_concept_context(doc, concept['text'])
            
            if context:
                # Create cloze deletion by replacing the concept with [...]
                cloze_text = context.replace(concept['text'], "[...]")
                
                # Create learning item
                item = LearningItem(
                    extract_id=extract_id,
                    item_type='cloze',
                    question=cloze_text,
                    answer=concept['text'],
                    priority=extract.priority,
                    created_date=datetime.utcnow()
                )
                
                self.db_session.add(item)
                learning_items.append(item)
        
        self.db_session.commit()
        return learning_items
    
    def _find_concept_context(self, doc, concept_text: str) -> str:
        """Find the sentence containing a concept."""
        for sent in doc.sents:
            if concept_text in sent.text:
                return sent.text
        return ""
    
    def suggest_related_extracts(self, extract_id: int, max_suggestions: int = 5) -> List[Dict[str, Any]]:
        """
        Suggest related extracts based on content similarity.
        
        Args:
            extract_id: ID of the source extract
            max_suggestions: Maximum number of suggestions to return
            
        Returns:
            List of dictionaries with related extract information
        """
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            logger.error(f"Extract not found: {extract_id}")
            return []
        
        # Get all extracts
        all_extracts = self.db_session.query(Extract).filter(
            Extract.id != extract_id
        ).all()
        
        if not all_extracts:
            return []
        
        # Create a corpus of extract content
        corpus = [e.content for e in all_extracts]
        corpus.insert(0, extract.content)  # Add source extract at index 0
        
        # Calculate TF-IDF
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(corpus)
        
        # Calculate similarity to source extract
        source_vector = tfidf_matrix[0:1]
        similarity_scores = (tfidf_matrix * source_vector.T).toarray().flatten()
        
        # Remove source extract score
        similarity_scores = similarity_scores[1:]
        
        # Get indices of top similar extracts
        top_indices = similarity_scores.argsort()[-max_suggestions:][::-1]
        
        # Create result
        result = []
        for idx in top_indices:
            extract_obj = all_extracts[idx]
            result.append({
                'id': extract_obj.id,
                'content': extract_obj.content[:100] + '...' if len(extract_obj.content) > 100 else extract_obj.content,
                'similarity': similarity_scores[idx],
                'document_id': extract_obj.document_id
            })
        
        return result
    
    def suggest_tags_for_extract(self, extract_id: int, max_suggestions: int = 5) -> List[str]:
        """
        Suggest tags for an extract based on content analysis.
        
        Args:
            extract_id: ID of the extract
            max_suggestions: Maximum number of tag suggestions to return
            
        Returns:
            List of suggested tag names
        """
        # Get the extract
        extract = self.db_session.query(Extract).get(extract_id)
        if not extract:
            logger.error(f"Extract not found: {extract_id}")
            return []
        
        # Get extract content
        content = extract.content
        if not content or len(content.strip()) < 10:
            return []
        
        # Process with spaCy
        doc = self.nlp(content)
        
        # Collect potential tags from different sources
        potential_tags = []
        
        # 1. Extract named entities as potential tags
        for ent in doc.ents:
            if ent.label_ in ['ORG', 'PERSON', 'GPE', 'LOC', 'PRODUCT', 'WORK_OF_ART', 'EVENT']:
                # Clean up the entity text
                tag_text = ent.text.strip().lower()
                # Remove any trailing punctuation
                tag_text = re.sub(r'[.,;:!?]$', '', tag_text)
                
                if tag_text and len(tag_text) > 2:  # Avoid too short tags
                    potential_tags.append({
                        'text': tag_text,
                        'source': 'entity',
                        'score': 0.8  # Higher score for entities
                    })
        
        # 2. Extract keywords using noun chunks
        for chunk in doc.noun_chunks:
            # Skip chunks that are too short or just pronouns
            if len(chunk.text) <= 2 or chunk.root.pos_ == 'PRON':
                continue
                
            # Clean up the chunk text
            tag_text = chunk.text.strip().lower()
            tag_text = re.sub(r'[.,;:!?]$', '', tag_text)
            
            # Only keep chunks that are not just articles or determiners
            if tag_text and not tag_text in ['the', 'a', 'an', 'this', 'that', 'these', 'those']:
                potential_tags.append({
                    'text': tag_text,
                    'source': 'noun_chunk',
                    'score': 0.6  # Medium score
                })
        
        # 3. Extract important single terms
        important_tokens = []
        for token in doc:
            # Keep only content words (nouns, verbs, adjectives, adverbs)
            if (token.pos_ in ['NOUN', 'PROPN', 'VERB', 'ADJ', 'ADV'] and 
                not token.is_stop and 
                len(token.text) > 3):
                
                # Lemmatize the token to get base form
                lemma = token.lemma_.lower()
                
                important_tokens.append({
                    'text': lemma,
                    'source': 'token',
                    'score': 0.3 + (0.1 * token.prob)  # Base score plus word probability
                })
        
        # Combine all potential tags
        all_potential_tags = potential_tags + important_tokens
        
        # Remove duplicates by keeping highest score
        unique_tags = {}
        for tag in all_potential_tags:
            text = tag['text']
            if text in unique_tags:
                if tag['score'] > unique_tags[text]['score']:
                    unique_tags[text] = tag
            else:
                unique_tags[text] = tag
        
        # Sort by score and return top N
        sorted_tags = sorted(unique_tags.values(), key=lambda x: x['score'], reverse=True)
        
        # Extract just the text for the final list
        return [tag['text'] for tag in sorted_tags[:max_suggestions]]
