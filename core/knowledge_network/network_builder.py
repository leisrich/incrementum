# core/knowledge_network/network_builder.py

import logging
from typing import Dict, Any, List, Tuple, Optional, Set
import math
import re

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import spacy
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import networkx as nx

from sqlalchemy import func
from sqlalchemy.orm import Session
from core.knowledge_base.models import Document, Extract, LearningItem, Category

logger = logging.getLogger(__name__)

class KnowledgeNetworkBuilder:
    """
    Build a knowledge network graph from the knowledge base,
    identifying relationships between extracts, documents, and concepts.
    """
    
    def __init__(self, db_session: Session):
        self.db_session = db_session
        
        # Initialize NLP resources
        try:
            nltk.data.find('tokenizers/punkt')
            nltk.data.find('corpora/stopwords')
            nltk.data.find('corpora/wordnet')
        except LookupError:
            nltk.download('punkt')
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
    
    def build_document_extract_graph(self, category_id: Optional[int] = None) -> nx.Graph:
        """
        Build a graph showing documents, extracts, and their relationships.
        
        Args:
            category_id: Optional category filter
            
        Returns:
            NetworkX graph object
        """
        G = nx.Graph()
        
        # Get documents (optionally filtered by category)
        documents_query = self.db_session.query(Document)
        if category_id:
            documents_query = documents_query.filter(Document.category_id == category_id)
        
        documents = documents_query.all()
        
        # Add document nodes
        for doc in documents:
            G.add_node(f"doc_{doc.id}", 
                       id=doc.id, 
                       title=doc.title, 
                       type="document",
                       size=10)  # Size based on importance
        
        # Get extracts from these documents
        extract_ids = set()
        for doc in documents:
            extracts = self.db_session.query(Extract).filter(
                Extract.document_id == doc.id
            ).all()
            
            # Add extract nodes and edges to document
            for extract in extracts:
                extract_ids.add(extract.id)
                G.add_node(f"ext_{extract.id}", 
                           id=extract.id, 
                           content=extract.content[:100] + "..." if len(extract.content) > 100 else extract.content,
                           type="extract",
                           priority=extract.priority,
                           size=5 + (extract.priority / 20))  # Size based on priority
                
                # Add edge between document and extract
                G.add_edge(f"doc_{doc.id}", f"ext_{extract.id}", 
                           weight=1.0, 
                           type="contains")
        
        # Find relationships between extracts based on content similarity
        self._add_extract_relationships(G, list(extract_ids))
        
        return G
    
    def build_concept_graph(self, min_extracts: int = 3) -> nx.Graph:
        """
        Build a graph of key concepts and their relationships.
        
        Args:
            min_extracts: Minimum number of extracts for a concept to be included
            
        Returns:
            NetworkX graph object
        """
        G = nx.Graph()
        
        # Extract key entities from all extracts
        extract_entities = self._extract_entities_from_all_extracts()
        
        # Count entity occurrences across extracts
        entity_counts = {}
        for extract_id, entities in extract_entities.items():
            for entity in entities:
                if entity not in entity_counts:
                    entity_counts[entity] = {
                        'count': 0,
                        'extracts': set()
                    }
                entity_counts[entity]['count'] += 1
                entity_counts[entity]['extracts'].add(extract_id)
        
        # Filter out entities that don't appear in enough extracts
        key_entities = {
            entity: data for entity, data in entity_counts.items() 
            if len(data['extracts']) >= min_extracts
        }
        
        # Add concept nodes
        for entity, data in key_entities.items():
            G.add_node(f"concept_{entity}",
                       label=entity,
                       type="concept",
                       count=data['count'],
                       size=math.log(data['count'] + 1) * 3)  # Size based on occurrence count
        
        # Add edges between concepts that co-occur in extracts
        for entity1, data1 in key_entities.items():
            for entity2, data2 in key_entities.items():
                if entity1 >= entity2:  # Avoid duplicate edges and self-loops
                    continue
                
                # Find extracts where both entities occur
                common_extracts = data1['extracts'].intersection(data2['extracts'])
                
                if common_extracts:
                    # Add edge with weight based on co-occurrence frequency
                    G.add_edge(f"concept_{entity1}", f"concept_{entity2}",
                               weight=len(common_extracts),
                               type="co-occurs")
        
        return G
    
    def build_learning_path(self, topic: str, depth: int = 3) -> nx.DiGraph:
        """
        Build a directed graph representing a learning path for a topic.
        
        Args:
            topic: The topic to create a learning path for
            depth: Depth of the learning path
            
        Returns:
            NetworkX directed graph object
        """
        G = nx.DiGraph()
        
        # Find relevant extracts for the topic
        relevant_extracts = self._find_relevant_extracts(topic)
        
        if not relevant_extracts:
            logger.warning(f"No relevant extracts found for topic: {topic}")
            return G
        
        # Sort by a simple "prerequisite" score - more basic items first
        # This is a simplified approach; a real implementation would be more sophisticated
        prerequisite_scores = self._calculate_prerequisite_scores(relevant_extracts)
        
        # Sort extracts by prerequisite score (ascending - lower score = more basic)
        sorted_extracts = sorted(
            [(id, score) for id, score in prerequisite_scores.items()],
            key=lambda x: x[1]
        )
        
        # Add nodes for topic and extracts
        G.add_node("topic", label=topic, type="topic", size=15)
        
        # Add top N extracts based on depth
        added_extracts = set()
        
        for extract_id, score in sorted_extracts[:depth]:
            extract = self.db_session.query(Extract).get(extract_id)
            if not extract:
                continue
                
            # Add extract node
            G.add_node(f"ext_{extract.id}",
                       id=extract.id,
                       content=extract.content[:100] + "..." if len(extract.content) > 100 else extract.content,
                       type="extract",
                       priority=extract.priority,
                       size=7)
            
            # Connect to topic
            G.add_edge("topic", f"ext_{extract.id}", type="related_to")
            
            added_extracts.add(extract.id)
        
        # Add prerequisite relationships between extracts
        for i, (ext_id1, _) in enumerate(sorted_extracts[:depth]):
            if ext_id1 not in added_extracts:
                continue
                
            for ext_id2, _ in sorted_extracts[i+1:depth]:
                if ext_id2 not in added_extracts:
                    continue
                    
                # Add directed edge from more basic to more advanced
                G.add_edge(f"ext_{ext_id1}", f"ext_{ext_id2}", type="prerequisite")
        
        return G
    
    def _add_extract_relationships(self, G: nx.Graph, extract_ids: List[int]) -> None:
        """
        Add edges between extracts based on content similarity.
        
        Args:
            G: NetworkX graph to add edges to
            extract_ids: List of extract IDs to analyze
        """
        if not extract_ids:
            return
        
        # Get extract contents
        extracts = self.db_session.query(Extract).filter(
            Extract.id.in_(extract_ids)
        ).all()
        
        if len(extracts) < 2:
            return
            
        # Create corpus of extract contents
        corpus = [extract.content for extract in extracts]
        id_map = {i: extract.id for i, extract in enumerate(extracts)}
        
        # Calculate TF-IDF
        vectorizer = TfidfVectorizer(stop_words='english')
        tfidf_matrix = vectorizer.fit_transform(corpus)
        
        # Calculate cosine similarity between all extracts
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # Add edges for similar extracts (similarity > 0.3)
        for i in range(len(extracts)):
            for j in range(i+1, len(extracts)):
                similarity = similarity_matrix[i, j]
                
                if similarity > 0.3:  # Threshold for meaningful similarity
                    G.add_edge(f"ext_{id_map[i]}", f"ext_{id_map[j]}",
                               weight=similarity,
                               type="similar")
    
    def _extract_entities_from_all_extracts(self) -> Dict[int, Set[str]]:
        """
        Extract key entities from all extracts.
        
        Returns:
            Dictionary mapping extract IDs to sets of entities
        """
        extracts = self.db_session.query(Extract).all()
        result = {}
        
        for extract in extracts:
            entities = self._extract_entities(extract.content)
            if entities:
                result[extract.id] = entities
        
        return result
    
    def _extract_entities(self, text: str) -> Set[str]:
        """
        Extract key entities from text.
        
        Args:
            text: Text to extract entities from
            
        Returns:
            Set of entity strings
        """
        # Process with spaCy
        doc = self.nlp(text)
        
        # Extract named entities
        entities = set()
        for ent in doc.ents:
            # Filter out very short entities and dates/numbers
            if len(ent.text) > 2 and ent.label_ not in ['DATE', 'TIME', 'PERCENT', 'MONEY', 'QUANTITY', 'CARDINAL', 'ORDINAL']:
                # Normalize entity text
                entity_text = ent.text.lower()
                entities.add(entity_text)
        
        # Extract key noun phrases
        for chunk in doc.noun_chunks:
            # Skip if it's just a pronoun or determiner
            if chunk.root.pos_ in ['PRON', 'DET']:
                continue
                
            # Skip very short phrases
            if len(chunk.text.split()) < 2:
                continue
                
            # Normalize noun phrase
            np_text = chunk.text.lower()
            # Remove determiners and stopwords from beginning
            np_text = re.sub(r'^(the|a|an|this|that|these|those)\s+', '', np_text)
            
            if len(np_text) > 2:
                entities.add(np_text)
        
        return entities
    
    def _find_relevant_extracts(self, topic: str) -> List[int]:
        """
        Find extracts relevant to a topic.
        
        Args:
            topic: Topic to find extracts for
            
        Returns:
            List of extract IDs
        """
        # Process topic with spaCy to get related terms
        doc = self.nlp(topic)
        
        # Get topic terms (including topic itself)
        topic_terms = [topic.lower()]
        
        # Add root and children of the topic in dependency tree
        for token in doc:
            topic_terms.append(token.text.lower())
            for child in token.children:
                topic_terms.append(child.text.lower())
        
        # Clean up terms
        topic_terms = [term for term in topic_terms if term not in self.stop_words and len(term) > 2]
        
        # Find extracts containing these terms
        relevant_extract_ids = set()
        
        for term in topic_terms:
            # Simple LIKE query - a real system would use full-text search
            extracts = self.db_session.query(Extract).filter(
                Extract.content.ilike(f"%{term}%")
            ).all()
            
            for extract in extracts:
                relevant_extract_ids.add(extract.id)
        
        return list(relevant_extract_ids)
    
    def _calculate_prerequisite_scores(self, extract_ids: List[int]) -> Dict[int, float]:
        """
        Calculate prerequisite scores for extracts.
        Lower score = more basic = should come earlier in learning path.
        
        Args:
            extract_ids: List of extract IDs
            
        Returns:
            Dictionary mapping extract IDs to prerequisite scores
        """
        scores = {}
        
        # Get extracts
        extracts = self.db_session.query(Extract).filter(
            Extract.id.in_(extract_ids)
        ).all()
        
        for extract in extracts:
            # Basic heuristics for scoring:
            # 1. Higher priority extracts get lower scores (basic important facts)
            priority_factor = 5 - (extract.priority / 25)  # Convert 0-100 to 1-5 range, reversed
            
            # 2. More technical/complex content gets higher scores
            complexity = self._calculate_text_complexity(extract.content)
            
            # 3. Content with more entities/concepts gets higher scores
            concept_count = len(self._extract_entities(extract.content))
            concept_factor = min(5, concept_count / 2)  # Cap at 5
            
            # Combine factors (with priority having most weight)
            score = (priority_factor * 0.5) + (complexity * 0.3) + (concept_factor * 0.2)
            scores[extract.id] = score
        
        return scores
    
    def _calculate_text_complexity(self, text: str) -> float:
        """
        Calculate complexity score for text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Complexity score (1-5 scale)
        """
        # Simple metrics:
        # 1. Average word length
        words = [word for word in word_tokenize(text.lower()) if word.isalpha()]
        if not words:
            return 1.0
            
        avg_word_length = sum(len(word) for word in words) / len(words)
        
        # 2. Sentence length
        sentences = nltk.sent_tokenize(text)
        if not sentences:
            return 1.0
            
        avg_sentence_length = len(words) / len(sentences)
        
        # Combine metrics (normalized to 1-5 scale)
        word_length_score = min(5, avg_word_length / 1.2)  # 6 letter avg = score of 5
        sentence_length_score = min(5, avg_sentence_length / 5)  # 25 words avg = score of 5
        
        return (word_length_score * 0.5) + (sentence_length_score * 0.5)


# ui/network_view.py

import os
import logging
from typing import Dict, Any, List, Optional
import math
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QLineEdit, QTabWidget,
    QGroupBox, QCheckBox, QSpinBox, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QSize, QUrl
from PyQt6.QtGui import QIcon
from PyQt6.QtWebEngineWidgets import QWebEngineView

import networkx as nx
from networkx.readwrite import json_graph

from core.knowledge_base.models import Category
from core.knowledge_network.network_builder import KnowledgeNetworkBuilder

logger = logging.getLogger(__name__)

class NetworkView(QWidget):
    """Widget for visualizing knowledge networks."""
    
    def __init__(self, db_session):
        super().__init__()
        
        self.db_session = db_session
        self.network_builder = KnowledgeNetworkBuilder(db_session)
        
        # Create UI
        self._create_ui()
    
    def _create_ui(self):
        """Create the UI layout."""
        main_layout = QVBoxLayout(self)
        
        # Controls area
        controls_layout = QHBoxLayout()
        
        # Graph type selector
        type_label = QLabel("Graph Type:")
        controls_layout.addWidget(type_label)
        
        self.graph_type_combo = QComboBox()
        self.graph_type_combo.addItems([
            "Document-Extract Network", 
            "Concept Network", 
            "Learning Path"
        ])
        self.graph_type_combo.currentIndexChanged.connect(self._on_graph_type_changed)
        controls_layout.addWidget(self.graph_type_combo)
        
        # Category filter
        category_label = QLabel("Category:")
        controls_layout.addWidget(category_label)
        
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        self._populate_categories()
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        controls_layout.addWidget(self.category_combo)
        
        # Topic input (for learning path)
        topic_label = QLabel("Topic:")
        controls_layout.addWidget(topic_label)
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("Enter topic for learning path")
        self.topic_input.setEnabled(False)  # Initially disabled
        controls_layout.addWidget(self.topic_input)
        
        # Generate button
        self.generate_button = QPushButton("Generate Graph")
        self.generate_button.clicked.connect(self._on_generate_graph)
        controls_layout.addWidget(self.generate_button)
        
        main_layout.addLayout(controls_layout)
        
        # Graph view
        self.web_view = QWebEngineView()
        main_layout.addWidget(self.web_view)
        
        # Generate initial graph
        self._on_generate_graph()
    
    def _populate_categories(self):
        """Populate the category selector."""
        categories = self.db_session.query(Category).all()
        
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
    
    @pyqtSlot(int)
    def _on_graph_type_changed(self, index):
        """Handle graph type change."""
        # Enable/disable topic input based on graph type
        is_learning_path = index == 2  # "Learning Path" option
        self.topic_input.setEnabled(is_learning_path)
    
    @pyqtSlot(int)
    def _on_category_changed(self, index):
        """Handle category change."""
        # This is just a filter change, no immediate action needed
        pass
    
    @pyqtSlot()
    def _on_generate_graph(self):
        """Generate and display the selected graph type."""
        graph_type = self.graph_type_combo.currentText()
        category_id = self.category_combo.currentData()
        
        try:
            if graph_type == "Document-Extract Network":
                G = self.network_builder.build_document_extract_graph(category_id)
            elif graph_type == "Concept Network":
                G = self.network_builder.build_concept_graph()
            elif graph_type == "Learning Path":
                topic = self.topic_input.text().strip()
                if not topic:
                    QMessageBox.warning(self, "Missing Topic", "Please enter a topic for the learning path.")
                    return
                G = self.network_builder.build_learning_path(topic)
            else:
                logger.error(f"Unknown graph type: {graph_type}")
                return
            
            # Display the graph
            self._display_graph(G, graph_type)
            
        except Exception as e:
            logger.exception(f"Error generating graph: {e}")
            QMessageBox.warning(self, "Error", f"Error generating graph: {str(e)}")
    
    def _display_graph(self, G: nx.Graph, title: str):
        """
        Display a NetworkX graph using D3.js visualization.
        
        Args:
            G: NetworkX graph to display
            title: Title for the graph
        """
        # Convert graph to JSON
        graph_data = json_graph.node_link_data(G)
        
        # Create HTML with D3.js visualization
        html = self._create_graph_html(graph_data, title)
        
        # Display in web view
        self.web_view.setHtml(html)
    
    def _create_graph_html(self, graph_data: Dict[str, Any], title: str) -> str:
        """
        Create HTML with D3.js visualization for the graph.
        
        Args:
            graph_data: Graph data in node-link format
            title: Title for the graph
            
        Returns:
            HTML string
        """
        # Convert graph data to JSON string
        graph_json = json.dumps(graph_data)
        
        # Create HTML with D3.js visualization
        # This is a simplified version - a real implementation would have more sophisticated visualization
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{title}</title>
            <script src="https://d3js.org/d3.v7.min.js"></script>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 0; }}
                .graph-container {{ width: 100%; height: 100vh; }}
                .node {{ stroke: #fff; stroke-width: 1.5px; }}
                .link {{ stroke: #999; stroke-opacity: 0.6; }}
                .node text {{ pointer-events: none; font-size: 10px; }}
                .tooltip {{ position: absolute; background: white; border: 1px solid #ccc; padding: 5px; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="graph-container" id="graph"></div>
            
            <script>
                // Graph data from Python
                const graphData = {graph_json};
                
                // Create force simulation
                const width = window.innerWidth;
                const height = window.innerHeight;
                
                const svg = d3.select("#graph")
                    .append("svg")
                    .attr("width", width)
                    .attr("height", height);
                
                // Define colors based on node types
                const colors = {{
                    "document": "#1f77b4",
                    "extract": "#ff7f0e",
                    "concept": "#2ca02c",
                    "topic": "#d62728"
                }};
                
                // Create tooltip
                const tooltip = d3.select("body").append("div")
                    .attr("class", "tooltip")
                    .style("opacity", 0);
                
                // Create force simulation
                const simulation = d3.forceSimulation(graphData.nodes)
                    .force("link", d3.forceLink(graphData.links).id(d => d.id))
                    .force("charge", d3.forceManyBody().strength(-300))
                    .force("center", d3.forceCenter(width / 2, height / 2))
                    .force("collide", d3.forceCollide().radius(d => (d.size || 5) * 2));
                
                // Create links
                const link = svg.append("g")
                    .selectAll("line")
                    .data(graphData.links)
                    .enter().append("line")
                    .attr("class", "link")
                    .attr("stroke-width", d => Math.sqrt(d.weight || 1));
                
                // Create nodes
                const node = svg.append("g")
                    .selectAll("circle")
                    .data(graphData.nodes)
                    .enter().append("circle")
                    .attr("class", "node")
                    .attr("r", d => d.size || 5)
                    .attr("fill", d => colors[d.type] || "#999")
                    .call(d3.drag()
                        .on("start", dragstarted)
                        .on("drag", dragged)
                        .on("end", dragended));
                
                // Add hover effects
                node.on("mouseover", function(event, d) {{
                    tooltip.transition()
                        .duration(200)
                        .style("opacity", .9);
                    
                    let tooltipHtml = "";
                    if (d.type === "document") {{
                        tooltipHtml = `<strong>Document:</strong> ${{d.title}}`;
                    }} else if (d.type === "extract") {{
                        tooltipHtml = `<strong>Extract:</strong><br>${{d.content}}`;
                    }} else if (d.type === "concept") {{
                        tooltipHtml = `<strong>Concept:</strong> ${{d.label}}`;
                    }} else if (d.type === "topic") {{
                        tooltipHtml = `<strong>Topic:</strong> ${{d.label}}`;
                    }}
                    
                    tooltip.html(tooltipHtml)
                        .style("left", (event.pageX + 10) + "px")
                        .style("top", (event.pageY - 28) + "px");
                }})
                .on("mouseout", function(d) {{
                    tooltip.transition()
                        .duration(500)
                        .style("opacity", 0);
                }});
                
                // Add node labels
                const labels = svg.append("g")
                    .selectAll("text")
                    .data(graphData.nodes)
                    .enter().append("text")
                    .attr("dx", 12)
                    .attr("dy", ".35em")
                    .text(d => {{
                        if (d.type === "document") return d.title;
                        if (d.type === "concept") return d.label;
                        if (d.type === "topic") return d.label;
                        return null;  // No labels for extracts to reduce clutter
                    }});
                
                // Update simulation on tick
                simulation.on("tick", () => {{
                    link
                        .attr("x1", d => d.source.x)
                        .attr("y1", d => d.source.y)
                        .attr("x2", d => d.target.x)
                        .attr("y2", d => d.target.y);
                    
                    node
                        .attr("cx", d => d.x)
                        .attr("cy", d => d.y);
                    
                    labels
                        .attr("x", d => d.x)
                        .attr("y", d => d.y);
                }});
                
                // Drag functions
                function dragstarted(event, d) {{
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                }}
                
                function dragged(event, d) {{
                    d.fx = event.x;
                    d.fy = event.y;
                }}
                
                function dragended(event, d) {{
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                }}
            </script>
        </body>
        </html>
        """
        
        return html
