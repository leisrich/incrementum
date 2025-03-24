# Creating Custom Themes for Incrementum

Incrementum provides flexible theming capabilities, allowing you to create and apply custom themes to personalize your experience. This guide explains how to create, modify, and apply custom themes.

## Theme Types

Incrementum supports two types of theme files:

1. **JSON Color Themes** - Define color values for different UI elements
2. **QSS Style Sheets** - Provide detailed styling rules using Qt Style Sheets

## Creating a Custom Theme

### Method 1: Using the Theme Template Generator

The easiest way to create a custom theme is to use the built-in theme template generator:

1. Open **Settings** from the Tools menu
2. Navigate to the **User Interface** tab
3. Click the **Browse...** button next to "Custom theme file"
4. Select **Create New Theme Template** from the dropdown
5. Choose a location and name for your theme file
6. Click **Save**

This will create a JSON theme template with pre-filled values that you can edit.

### Method 2: Manually Creating a Theme File

#### JSON Color Theme

Create a JSON file with the following structure:

```json
{
    "window": "#2D2D30",
    "windowText": "#FFFFFF",
    "base": "#252526",
    "alternateBase": "#3C3C3C",
    "text": "#FFFFFF",
    "button": "#3C3C3C",
    "buttonText": "#FFFFFF",
    "brightText": "#FFFFFF",
    "highlight": "#264F78",
    "highlightedText": "#FFFFFF",
    "link": "#4EB8FF",
    "midLight": "#3C3C3C",
    "dark": "#1E1E1E",
    "mid": "#2D2D30",
    "shadow": "#1A1A1A",
    "light": "#505050"
}
```

The `colors` section defines colors for each UI element. You can modify these values using:
- Hex color codes (e.g., `#FFFFFF`)
- RGB values (e.g., `rgb(255, 255, 255)`)
- RGBA values (e.g., `rgba(255, 255, 255, 0.5)`)
- Named colors (e.g., `blue`, `red`)

#### QSS Style Sheet

Create a `.qss` file with Qt Style Sheet syntax:

```css
/* Main application styles */
QWidget {
    background-color: #2D2D30;
    color: #FFFFFF;
}

QPushButton {
    background-color: #3C3C3C;
    color: #FFFFFF;
    border: 1px solid #1E1E1E;
    padding: 5px;
    border-radius: 3px;
}

QPushButton:hover {
    background-color: #505050;
}

/* Document view styles */
DocumentView QTextEdit {
    background-color: #252526;
    color: #FFFFFF;
    border: none;
}

/* Add more selectors and styles as needed */
```

QSS files provide more detailed styling control but require knowledge of Qt Style Sheet syntax.

## Theme File Location

Theme files are stored in:

```
~/.incrementum/themes/
```

You can place your theme files in this directory to make them available across restarts.

## Applying a Custom Theme

1. Open **Settings** from the Tools menu
2. Navigate to the **User Interface** tab
3. Choose one of the following methods:
   - Select a custom theme from the "Theme" dropdown (if placed in the themes directory)
   - Click **Browse...** to select a theme file from any location

Your selected theme will be previewed immediately in the settings dialog. Click **Apply** or **OK** to apply it to the entire application.

## Exporting and Sharing Themes

To share your custom theme with others:

1. Create and test your theme file
2. Copy the `.json` or `.qss` file from `~/.incrementum/themes/`
3. Share the file

Other users can import your theme by placing it in their themes directory or browsing to it in the settings dialog.

## Advanced: Creating a Combined Theme

For maximum customization, you can create both a JSON color theme and a QSS stylesheet with the same base name:

```
mytheme.json  - For basic color palette
mytheme.qss   - For detailed styling
```

When you select the JSON theme file, Incrementum will automatically look for and apply the matching QSS file as well.

## Tips for Theme Creation

1. Start by modifying an existing theme rather than starting from scratch
2. Test your theme with different views and dialogs to ensure good contrast
3. Consider accessibility - ensure text remains readable against backgrounds
4. Use the theme preview feature to test before applying
5. Backup your theme file before making significant changes 
