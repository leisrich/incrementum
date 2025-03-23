import os
import re
import logging
import html
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from core.knowledge_base.models import Document, Extract, WebHighlight, IncrementalReading

logger = logging.getLogger(__name__)

class SuperMemoHTMLExporter:
    """
    Exports extracts and highlights to SuperMemo-compatible HTML format.
    This allows users to import the content into SuperMemo for further learning.
    """
    
    def __init__(self, db_session):
        """Initialize with database session."""
        self.db_session = db_session
    
    def export_document_extracts(self, document_id: int, output_path: str) -> Optional[str]:
        """
        Export all extracts from a document as a SuperMemo HTML file.
        
        Args:
            document_id: ID of the document to export extracts from
            output_path: Directory to save the output file
            
        Returns:
            Path to the exported HTML file or None if failed
        """
        try:
            # Get document
            document = self.db_session.query(Document).get(document_id)
            if not document:
                logger.error(f"Document not found: {document_id}")
                return None
                
            # Get extracts
            extracts = self.db_session.query(Extract)\
                .filter(Extract.document_id == document_id)\
                .order_by(Extract.created_date)\
                .all()
                
            if not extracts:
                logger.warning(f"No extracts found for document: {document_id}")
                return None
                
            # Get highlights
            highlights = self.db_session.query(WebHighlight)\
                .filter(WebHighlight.document_id == document_id)\
                .order_by(WebHighlight.created_date)\
                .all()
                
            # Create HTML content
            html_content = self._generate_supermemo_html(document, extracts, highlights)
            
            # Create output filename
            safe_title = re.sub(r'[^\w\-\.]', '_', document.title)
            filename = f"{safe_title}_extracts.html"
            output_file = os.path.join(output_path, filename)
            
            # Write to file
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            logger.info(f"Exported SuperMemo HTML to: {output_file}")
            return output_file
            
        except Exception as e:
            logger.exception(f"Error exporting SuperMemo HTML: {e}")
            return None
    
    def export_reading_queue(self, output_path: str, limit: int = 20) -> Optional[str]:
        """
        Export the incremental reading queue as a SuperMemo HTML file.
        
        Args:
            output_path: Directory to save the output file
            limit: Maximum number of items to include
            
        Returns:
            Path to the exported HTML file or None if failed
        """
        try:
            # Get reading items
            readings = self.db_session.query(IncrementalReading, Document)\
                .join(Document, Document.id == IncrementalReading.document_id)\
                .order_by(IncrementalReading.reading_priority.desc())\
                .limit(limit)\
                .all()
                
            if not readings:
                logger.warning("No reading items found in queue")
                return None
                
            # Create HTML content
            html_content = self._generate_reading_queue_html(readings)
            
            # Create output filename
            timestamp = datetime.now().strftime("%Y%m%d")
            output_file = os.path.join(output_path, f"reading_queue_{timestamp}.html")
            
            # Write to file
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            logger.info(f"Exported reading queue to: {output_file}")
            return output_file
            
        except Exception as e:
            logger.exception(f"Error exporting reading queue: {e}")
            return None
    
    def _generate_supermemo_html(self, document: Document, 
                                extracts: List[Extract], 
                                highlights: List[WebHighlight]) -> str:
        """Generate SuperMemo-compatible HTML content."""
        # Create HTML header
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{html.escape(document.title)}</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }}
        h1 {{ color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
        .extract {{ margin: 15px 0; padding: 15px; background-color: #f9f9f9; border-left: 4px solid #3498db; }}
        .highlight {{ margin: 15px 0; padding: 15px; background-color: #fffacd; border-left: 4px solid #f1c40f; }}
        .context {{ color: #777; font-size: 0.9em; margin-top: 10px; padding: 10px; background-color: #f0f0f0; }}
        .metadata {{ font-size: 0.8em; color: #888; margin-top: 5px; }}
        .document-info {{ background-color: #eee; padding: 10px; margin-bottom: 20px; }}
        .sm-priority {{ font-weight: bold; color: #e74c3c; }}
    </style>
</head>
<body>
    <div class="document-info">
        <h1>{html.escape(document.title)}</h1>
        <p><strong>Source:</strong> {html.escape(document.source_url or "")}</p>
        <p><strong>Author:</strong> {html.escape(document.author or "")}</p>
        <p><strong>Imported:</strong> {document.imported_date.strftime('%Y-%m-%d') if document.imported_date else ""}</p>
    </div>
    <h2>Extracts and Highlights</h2>
"""
        
        # Add extracts
        for extract in extracts:
            priority_html = f'<span class="sm-priority">[P: {extract.priority}]</span> ' if extract.priority else ''
            html_content += f"""
    <div class="extract">
        <div>{priority_html}{html.escape(extract.content)}</div>
        <div class="metadata">Created: {extract.created_date.strftime('%Y-%m-%d %H:%M') if extract.created_date else ""}</div>
    </div>
"""
        
        # Add highlights
        for highlight in highlights:
            html_content += f"""
    <div class="highlight">
        <div>{html.escape(highlight.content)}</div>
"""
            if highlight.context:
                html_content += f'        <div class="context">{html.escape(highlight.context)}</div>\n'
                
            html_content += f"""        <div class="metadata">Created: {highlight.created_date.strftime('%Y-%m-%d %H:%M') if highlight.created_date else ""}</div>
    </div>
"""
        
        # Close HTML
        html_content += """
</body>
</html>
"""
        return html_content
    
    def _generate_reading_queue_html(self, readings: List[Tuple[IncrementalReading, Document]]) -> str:
        """Generate HTML for the reading queue."""
        # Create HTML header
        html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Incremental Reading Queue</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; margin: 20px; }
        h1 { color: #2c3e50; border-bottom: 1px solid #eee; padding-bottom: 10px; }
        .reading-item { margin: 20px 0; padding: 15px; background-color: #f9f9f9; border-left: 4px solid #3498db; }
        .item-title { font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }
        .item-info { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-top: 15px; }
        .info-field { background-color: #eee; padding: 5px 10px; }
        .priority-high { border-left-color: #e74c3c; }
        .priority-medium { border-left-color: #f39c12; }
        .priority-low { border-left-color: #3498db; }
        .progress-bar { height: 10px; background-color: #ecf0f1; margin-top: 10px; }
        .progress-fill { height: 100%; background-color: #2ecc71; }
    </style>
</head>
<body>
    <h1>Incremental Reading Queue</h1>
    <p>Generated: {}</p>
""".format(datetime.now().strftime('%Y-%m-%d %H:%M'))
        
        # Add reading items
        for reading, document in readings:
            # Determine priority class
            priority_class = "priority-medium"
            if reading.reading_priority >= 70:
                priority_class = "priority-high"
            elif reading.reading_priority <= 30:
                priority_class = "priority-low"
                
            # Format dates
            next_read = reading.next_read_date.strftime('%Y-%m-%d') if reading.next_read_date else "Not scheduled"
            last_read = reading.last_read_date.strftime('%Y-%m-%d') if reading.last_read_date else "Never"
            
            html_content += f"""
    <div class="reading-item {priority_class}">
        <div class="item-title">{html.escape(document.title)}</div>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {reading.percent_complete}%;"></div>
        </div>
        <div class="item-info">
            <div class="info-field"><strong>Priority:</strong> {reading.reading_priority:.1f}</div>
            <div class="info-field"><strong>Next Reading:</strong> {next_read}</div>
            <div class="info-field"><strong>Last Read:</strong> {last_read}</div>
            <div class="info-field"><strong>Progress:</strong> {reading.percent_complete:.1f}%</div>
            <div class="info-field"><strong>Repetitions:</strong> {reading.repetitions}</div>
            <div class="info-field"><strong>Interval:</strong> {reading.interval} days</div>
        </div>
        <div class="item-source">
            <p><strong>Source:</strong> <a href="{html.escape(document.source_url or '')}">{html.escape(document.source_url or '')}</a></p>
        </div>
    </div>
"""
        
        # Close HTML
        html_content += """
</body>
</html>
"""
        return html_content 