#!/bin/bash
echo "Packaging Incrementum for macOS..."
python3 package.py --platform macos --clean
echo ""
echo "If the packaging was successful, you can find the app at:"
echo "    dist/Incrementum.app"
echo "" 