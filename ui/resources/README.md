# Incrementum Resources

This directory contains resources used by the Incrementum application, such as:

- StyleSheets (QSS files)
- Icons 
- Images
- Other static assets

## Dark Theme

The application includes a modern dark theme (`dark_theme.qss`) that provides a comfortable reading and learning experience, especially during long study sessions. 

The dark theme features:

- Dark background with blue accents
- Reduced eye strain for night-time studying
- Consistent styling across all UI components
- Special styling for learning components like review cards and statistics
- Optimized contrast for better readability
- Responsive design elements for different screen sizes

### How to Apply the Theme

The theme is applied automatically by the `ThemeManager` class in the main window:

```python
self.theme_manager = ThemeManager(self.settings_manager)
self.theme_manager.apply_theme("dark_theme")
```

### Customizing UI Elements

The theme includes several custom classes you can use to style your UI elements:

- `.card-widget` - Creates a card-like container
- `.card-title` - Styled title for cards
- `.feature-card` - Highlighted feature cards
- `.stats-card` - Cards for displaying statistics
- `.extract-card` - Cards for extract display
- `.priority-high`, `.priority-medium`, `.priority-low` - Color-coded priority indicators
- `.review-button[difficulty="easy|good|hard|again"]` - Styled buttons for review responses

Example usage:

```python
# Style a widget as a card
my_widget.setProperty("class", "card-widget")

# Create a primary button
my_button.setObjectName("primaryButton")

# Style a review button
review_button.setProperty("class", "review-button")
review_button.setProperty("difficulty", "good")
```

## Adding Icons

To add new icons to the application:

1. Place the icon files (SVG or PNG) in the `icons` directory
2. Register them in the resource file if using Qt's resource system
3. Reference them in your code using:

```python
QIcon(":/icons/icon_name.png")
```

Or if loading directly from the filesystem:

```python
QIcon(os.path.join(os.path.dirname(__file__), "icons", "icon_name.png"))
```

## Custom Stylesheet Elements

The dark theme includes some CSS animations that can be applied using QPropertyAnimation:

- `fadeIn` - Fade in animation
- `slideInFromRight` - Slide in from right animation
- `pulse` - Pulsing background animation

## Troubleshooting Theme Issues

If elements aren't styled correctly:

1. Check that the object name or class property is set correctly
2. Verify that the QSS selector matches your widget hierarchy
3. Ensure the theme stylesheet is being loaded properly
4. Use Qt's style inspector tools to debug styling issues

For more information about Qt styling, refer to the [Qt Style Sheets Reference](https://doc.qt.io/qt-6/stylesheet-reference.html). 