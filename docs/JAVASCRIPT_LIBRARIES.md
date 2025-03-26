# Using JavaScript Libraries in Incrementum Documents

Incrementum now supports several popular JavaScript libraries that can be automatically loaded when they are detected in your documents. This allows you to create rich, interactive content with diagrams, mathematical formulas, 3D graphics, and more.

## Supported Libraries

The following JavaScript libraries are supported:

1. **Markdown (marked.js)** - For Markdown syntax rendering
2. **Mermaid.js** - For diagrams and charts
3. **KaTeX** - For mathematical formulas and equations
4. **Plotly.js** - For interactive plots and graphs
5. **Three.js** - For 3D visualizations

## How to Use

Incrementum will automatically detect markers for these libraries in your HTML or EPUB content and load the appropriate libraries. Here's how to use each one:

### Markdown

To use Markdown, wrap your content in a div with class "markdown":

```html
<div class="markdown">
# Heading
This is **bold** text and this is *italic* text.

- List item 1
- List item 2
</div>
```

### Mermaid

To create diagrams with Mermaid, use the "mermaid" class:

```html
<pre class="mermaid">
graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Process]
    B -->|No| D[Skip]
</pre>
```

Common diagram types:
- flowcharts (`graph TD`)
- sequence diagrams (`sequenceDiagram`)
- Gantt charts (`gantt`)
- class diagrams (`classDiagram`)

### KaTeX (Math Formulas)

To display mathematical formulas, use the "math" class:

```html
<div class="math">
E = mc^2
</div>
```

For inline math, use:

```html
<span class="math-inline">E = mc^2</span>
```

### Plotly.js

To use Plotly for interactive charts:

```html
<div id="my-plot" style="width:100%;height:400px;"></div>
<script>
    document.addEventListener('DOMContentLoaded', function() {
        if (typeof Plotly !== 'undefined') {
            var data = [{
                x: [1, 2, 3, 4, 5],
                y: [1, 4, 9, 16, 25],
                type: 'scatter'
            }];
            Plotly.newPlot('my-plot', data);
        }
    });
</script>
```

### Three.js

For 3D visualizations:

```html
<div id="three-container" style="width:100%;height:400px;"></div>
<script>
    document.addEventListener('DOMContentLoaded', function() {
        if (typeof THREE !== 'undefined') {
            var scene = new THREE.Scene();
            var camera = new THREE.PerspectiveCamera(75, window.innerWidth/window.innerHeight, 0.1, 1000);
            var renderer = new THREE.WebGLRenderer();
            renderer.setSize(document.getElementById('three-container').clientWidth, 400);
            document.getElementById('three-container').appendChild(renderer.domElement);
            
            var geometry = new THREE.BoxGeometry(1, 1, 1);
            var material = new THREE.MeshBasicMaterial({color: 0x00ff00});
            var cube = new THREE.Mesh(geometry, material);
            scene.add(cube);
            
            camera.position.z = 5;
            
            function animate() {
                requestAnimationFrame(animate);
                cube.rotation.x += 0.01;
                cube.rotation.y += 0.01;
                renderer.render(scene, camera);
            }
            animate();
        }
    });
</script>
```

## Example File

You can find an example of all these libraries in action in the `test_javascript_libraries.html` file included with Incrementum.

## Tips for Best Results

1. Wrap scripts in a `DOMContentLoaded` event listener to ensure they run after the page loads
2. Always check if the library is available before using it (e.g., `if (typeof THREE !== 'undefined')`)
3. For EPUB documents, make sure all resources are relative paths
4. You can combine multiple libraries in the same document
5. All libraries are loaded from CDNs, so an internet connection is required

## Library Versions

The following library versions are used:

- Marked.js: Latest from cdn.jsdelivr.net
- Mermaid.js: Latest from cdn.jsdelivr.net
- KaTeX: v0.16.8
- Plotly.js: Latest
- Three.js: v0.157.0

## Troubleshooting

If libraries don't load or don't render correctly:

1. Check browser console for errors (available in developer tools)
2. Verify that your document's HTML is well-formed
3. Make sure the library markers are present in your document
4. If using Three.js, check that WebGL is supported in your browser

For more help, please refer to the documentation of each library. 