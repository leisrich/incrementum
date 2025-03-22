#!/usr/bin/env python3
"""
Generate application icons for Incrementum.
Creates icons in various formats and sizes for different platforms.
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Create output directories
ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
os.makedirs(ICON_DIR, exist_ok=True)

# Icon sizes needed for different platforms
ICON_SIZES = {
    'windows': [16, 32, 48, 64, 128, 256],  # ICO format supports multiple sizes
    'macos': [16, 32, 64, 128, 256, 512, 1024],  # ICNS needs these sizes
    'linux': [16, 22, 24, 32, 48, 64, 128, 256]  # Various sizes for different Linux DEs
}

# Base colors
PRIMARY_COLOR = (70, 130, 180)  # Steel blue
SECONDARY_COLOR = (255, 255, 255)  # White
ACCENT_COLOR = (255, 215, 0)  # Gold

def create_brain_icon(size):
    """Create a brain icon with learning symbols"""
    # Create a square image with transparent background
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Calculate dimensions based on size
    padding = int(size * 0.1)
    center = size // 2
    radius = (size - 2 * padding) // 2
    
    # Draw a circular background
    draw.ellipse(
        (padding, padding, size - padding, size - padding),
        fill=PRIMARY_COLOR
    )
    
    # Draw brain-like shape
    brain_width = int(radius * 1.3)
    brain_height = int(radius * 1.5)
    brain_top = center - brain_height // 2
    brain_left = center - brain_width // 2
    
    # Draw the cerebrum (top of brain) - simplified as curves
    for i in range(4):
        curve_x = brain_left + (i * brain_width // 3)
        draw.arc(
            (curve_x, brain_top, curve_x + brain_width // 2, brain_top + brain_height // 2),
            180, 0,
            fill=SECONDARY_COLOR,
            width=max(1, size // 32)
        )
    
    # Draw cerebellum (bottom of brain) - simplified
    draw.arc(
        (brain_left, brain_top + brain_height // 2, 
         brain_left + brain_width, brain_top + brain_height),
        0, 180,
        fill=SECONDARY_COLOR,
        width=max(1, size // 32)
    )
    
    # Draw a lightbulb symbol (for ideas/learning)
    bulb_size = radius // 2
    bulb_top = brain_top - bulb_size // 2
    
    # Bulb glass
    draw.ellipse(
        (center - bulb_size // 2, bulb_top, 
         center + bulb_size // 2, bulb_top + bulb_size),
        fill=ACCENT_COLOR
    )
    
    # Bulb base
    base_width = bulb_size // 3
    base_height = bulb_size // 2
    draw.rectangle(
        (center - base_width // 2, bulb_top + bulb_size, 
         center + base_width // 2, bulb_top + bulb_size + base_height),
        fill=ACCENT_COLOR
    )
    
    # Draw some "connection" lines to symbolize learning/knowledge network
    line_width = max(1, size // 64)
    for i in range(3):
        angle = 30 + i * 60
        x_offset = int(radius * 0.7 * (i % 2 * 2 - 1))
        y_offset = int(radius * 0.5 * ((i+1) % 2 * 2 - 1))
        
        draw.line(
            (center, center, center + x_offset, center + y_offset),
            fill=SECONDARY_COLOR,
            width=line_width
        )
        # Draw a small circle at the end
        node_radius = max(1, size // 24)
        draw.ellipse(
            (center + x_offset - node_radius, center + y_offset - node_radius,
             center + x_offset + node_radius, center + y_offset + node_radius),
            fill=ACCENT_COLOR
        )
    
    # Apply a slight blur for a softer look
    img = img.filter(ImageFilter.GaussianBlur(radius=size/128))
    
    return img

def generate_all_icons():
    """Generate icons for all platforms in all required sizes"""
    # Get all needed sizes without duplicates
    all_sizes = set()
    for sizes in ICON_SIZES.values():
        all_sizes.update(sizes)
    
    # Generate each size once
    size_to_icon = {}
    for size in sorted(all_sizes):
        print(f"Generating {size}x{size} icon...")
        size_to_icon[size] = create_brain_icon(size)
    
    # Save individual PNG files
    for size, icon in size_to_icon.items():
        icon.save(os.path.join(ICON_DIR, f"incrementum_{size}.png"))
    
    # Create a .ico file for Windows (supports multiple sizes in one file)
    windows_icons = [size_to_icon[size] for size in ICON_SIZES['windows']]
    windows_icons[0].save(
        os.path.join(ICON_DIR, "incrementum.ico"),
        sizes=[(size, size) for size in ICON_SIZES['windows']],
        format="ICO"
    )
    
    # Create a composite large icon for other uses
    largest_size = max(all_sizes)
    largest_icon = size_to_icon[largest_size]
    largest_icon.save(os.path.join(ICON_DIR, "incrementum.png"))
    
    print(f"Icons generated and saved to {ICON_DIR}")

if __name__ == "__main__":
    generate_all_icons() 