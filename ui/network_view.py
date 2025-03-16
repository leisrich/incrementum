# ui/network_view.py

import os
import logging
import json
import tempfile
from typing import Dict, Any, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QComboBox, QLineEdit, QTabWidget,
    QGroupBox, QCheckBox, QSpinBox, QMessageBox,
    QSlider, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot, QUrl, QSize
from PyQt6.QtGui import QIcon, QColor

import networkx as nx
from networkx.readwrite import json_graph

# Try to import WebEngine for visualization
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    WEB_ENGINE_AVAILABLE = True
except ImportError:
    WEB_ENGINE_AVAILABLE = False
    logging.warning("QtWebEngineWidgets not available. Using fallback visualization.")

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
        
        # Export button
        self.export_button = QPushButton("Export Graph")
        self.export_button.clicked.connect(self._on_export_graph)
        controls_layout.addWidget(self.export_button)
        
        main_layout.addLayout(controls_layout)
        
        # Graph view
        if WEB_ENGINE_AVAILABLE:
            self.web_view = QWebEngineView()
            main_layout.addWidget(self.web_view)
        else:
            # Fallback for when WebEngine is not available
            self.fallback_view = QLabel("QtWebEngineWidgets not available. Please install PyQt6-WebEngine to view graphs.")
            self.fallback_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fallback_view.setStyleSheet("background-color: white; padding: 20px; font-size: 16px;")
            main_layout.addWidget(self.fallback_view)
        
        # Status bar
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)
        
        # Set initial graph type
        self._on_graph_type_changed(0)
    
    def _populate_categories(self):
        """Populate the category selector."""
        categories = self.db_session.query(Category).all()
        
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
    
    @pyqtSlot(int)
    def _on_graph_type_changed(self, index):
        """Handle graph type selection change."""
        # Enable/disable topic input based on graph type
        is_learning_path = index == 2  # "Learning Path" option
        self.topic_input.setEnabled(is_learning_path)
        
        # Update status
        graph_type = self.graph_type_combo.currentText()
        self.status_label.setText(f"Selected graph type: {graph_type}")
        
        # Clear previous graph
        if WEB_ENGINE_AVAILABLE:
            self.web_view.setHtml("")
    
    @pyqtSlot(int)
    def _on_category_changed(self, index):
        """Handle category change."""
        category_id = self.category_combo.currentData()
        category_name = self.category_combo.currentText()
        
        # Update status
        self.status_label.setText(f"Selected category: {category_name}")
    
    @pyqtSlot()
    def _on_generate_graph(self):
        """Generate and display the selected graph type."""
        self.status_label.setText("Generating graph...")
        
        graph_type = self.graph_type_combo.currentText()
        category_id = self.category_combo.currentData()
        
        try:
            if graph_type == "Document-Extract Network":
                G = self.network_builder.build_document_extract_graph(category_id)
            elif graph_type == "Concept Network":
                # For concept graph, use minimum extracts setting
                min_extracts = 3  # Default value
                G = self.network_builder.build_concept_graph(min_extracts)
            elif graph_type == "Learning Path":
                topic = self.topic_input.text().strip()
                if not topic:
                    QMessageBox.warning(self, "Missing Topic", "Please enter a topic for the learning path.")
                    self.status_label.setText("Missing topic")
                    return
                G = self.network_builder.build_learning_path(topic)
            else:
                logger.error(f"Unknown graph type: {graph_type}")
                self.status_label.setText(f"Error: Unknown graph type")
                return
            
            # Display the graph
            if WEB_ENGINE_AVAILABLE:
                self._display_graph(G, graph_type)
                self.status_label.setText(f"Generated {graph_type} with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges")
            else:
                self.status_label.setText(f"Generated graph (not displayed): {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
            
        except Exception as e:
            logger.exception(f"Error generating graph: {e}")
            self.status_label.setText(f"Error generating graph: {str(e)}")
            QMessageBox.warning(self, "Error", f"Error generating graph: {str(e)}")
    
    @pyqtSlot()
    def _on_export_graph(self):
        """Export the current graph to a file."""
        # Check if there's an active graph
        if not hasattr(self, '_current_graph') or not self._current_graph:
            QMessageBox.warning(self, "No Graph", "Please generate a graph first before exporting.")
            return
        
        # Get file path
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Graph", "", "GraphML Files (*.graphml);;JSON Files (*.json)"
        )
        
        if not filepath:
            return
        
        try:
            # Export based on file extension
            if filepath.endswith(".graphml"):
                # Export to GraphML
                nx.write_graphml(self._current_graph, filepath)
            else:
                # Default to JSON
                if not filepath.endswith(".json"):
                    filepath += ".json"
                
                # Export to JSON
                with open(filepath, 'w') as f:
                    json.dump(json_graph.node_link_data(self._current_graph), f, indent=2)
            
            self.status_label.setText(f"Graph exported to {filepath}")
            QMessageBox.information(self, "Export Successful", f"Graph exported to {filepath}")
            
        except Exception as e:
            logger.exception(f"Error exporting graph: {e}")
            self.status_label.setText(f"Error exporting graph: {str(e)}")
            QMessageBox.warning(self, "Export Error", f"Error exporting graph: {str(e)}")
    
    def _display_graph(self, G: nx.Graph, title: str):
        """
        Display a NetworkX graph using D3.js visualization.
        
        Args:
            G: NetworkX graph to display
            title: Title for the graph
        """
        # Save reference to current graph
        self._current_graph = G
        
        # Convert graph to JSON
        graph_data = json_graph.node_link_data(G)
        
        # Create HTML with D3.js visualization
        html = self._create_graph_html(graph_data, title)
        
        # Display in web view
        if WEB_ENGINE_AVAILABLE:
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


class SimpleNetworkView(QWidget):
    """Fallback widget for visualizing knowledge networks when WebEngine is not available."""
    
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
        controls_layout.addWidget(self.graph_type_combo)
        
        # Category filter
        category_label = QLabel("Category:")
        controls_layout.addWidget(category_label)
        
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories", None)
        self._populate_categories()
        controls_layout.addWidget(self.category_combo)
        
        # Topic input (for learning path)
        topic_label = QLabel("Topic:")
        controls_layout.addWidget(topic_label)
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("Enter topic for learning path")
        controls_layout.addWidget(self.topic_input)
        
        # Generate button
        self.generate_button = QPushButton("Generate Graph")
        self.generate_button.clicked.connect(self._on_generate_graph)
        controls_layout.addWidget(self.generate_button)
        
        # Export button
        self.export_button = QPushButton("Export Graph")
        self.export_button.clicked.connect(self._on_export_graph)
        controls_layout.addWidget(self.export_button)
        
        main_layout.addLayout(controls_layout)
        
        # Fallback view area
        info_area = QGroupBox("Graph Information")
        info_layout = QVBoxLayout(info_area)
        
        self.info_label = QLabel(
            "WebEngine visualization is not available. "
            "You can still generate and export graphs, but they will not be displayed. "
            "Install PyQt6-WebEngine for visual graph display."
        )
        self.info_label.setWordWrap(True)
        info_layout.addWidget(self.info_label)
        
        self.stats_label = QLabel("No graph generated yet.")
        info_layout.addWidget(self.stats_label)
        
        main_layout.addWidget(info_area)
        
        # Status bar
        self.status_label = QLabel("Ready")
        main_layout.addWidget(self.status_label)
    
    def _populate_categories(self):
        """Populate the category selector."""
        categories = self.db_session.query(Category).all()
        
        for category in categories:
            self.category_combo.addItem(category.name, category.id)
    
    @pyqtSlot()
    def _on_generate_graph(self):
        """Generate the selected graph type."""
        self.status_label.setText("Generating graph...")
        
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
                    self.status_label.setText("Missing topic")
                    return
                G = self.network_builder.build_learning_path(topic)
            else:
                logger.error(f"Unknown graph type: {graph_type}")
                self.status_label.setText(f"Error: Unknown graph type")
                return
            
            # Store current graph
            self._current_graph = G
            
            # Update stats
            nodes_count = G.number_of_nodes()
            edges_count = G.number_of_edges()
            self.stats_label.setText(
                f"Graph generated:\n"
                f"- Type: {graph_type}\n"
                f"- Nodes: {nodes_count}\n"
                f"- Edges: {edges_count}\n"
                f"- Node types: {', '.join(set(nx.get_node_attributes(G, 'type').values()))}"
            )
            
            self.status_label.setText(f"Generated {graph_type} with {nodes_count} nodes and {edges_count} edges")
            
        except Exception as e:
            logger.exception(f"Error generating graph: {e}")
            self.status_label.setText(f"Error generating graph: {str(e)}")
            QMessageBox.warning(self, "Error", f"Error generating graph: {str(e)}")
    
    @pyqtSlot()
    def _on_export_graph(self):
        """Export the current graph to a file."""
        # Check if there's an active graph
        if not hasattr(self, '_current_graph') or not self._current_graph:
            QMessageBox.warning(self, "No Graph", "Please generate a graph first before exporting.")
            return
        
        # Get file path
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Graph", "", "GraphML Files (*.graphml);;JSON Files (*.json)"
        )
        
        if not filepath:
            return
        
        try:
            # Export based on file extension
            if filepath.endswith(".graphml"):
                # Export to GraphML
                nx.write_graphml(self._current_graph, filepath)
            else:
                # Default to JSON
                if not filepath.endswith(".json"):
                    filepath += ".json"
                
                # Export to JSON
                with open(filepath, 'w') as f:
                    json.dump(json_graph.node_link_data(self._current_graph), f, indent=2)
            
            self.status_label.setText(f"Graph exported to {filepath}")
            QMessageBox.information(self, "Export Successful", f"Graph exported to {filepath}")
            
        except Exception as e:
            logger.exception(f"Error exporting graph: {e}")
            self.status_label.setText(f"Error exporting graph: {str(e)}")
            QMessageBox.warning(self, "Export Error", f"Error exporting graph: {str(e)}")
