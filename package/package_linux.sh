#!/bin/bash
echo "Packaging Incrementum for Linux..."
python3 package.py --platform linux --clean
echo ""
echo "If the packaging was successful, you can find the executable at:"
echo "    dist/Incrementum"
echo ""
echo "To run the application:"
echo "    chmod +x dist/Incrementum"
echo "    ./dist/Incrementum" 