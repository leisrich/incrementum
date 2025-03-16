#!/bin/bash
# run.sh - Script to run the Incrementum application

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3 and try again."
    exit 1
fi

# Check for virtual environment
if [ ! -d "incrementum-env" ]; then
    echo "Creating virtual environment..."
    python3 -m venv incrementum-env
    
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment. Please install python3-venv package and try again."
        exit 1
    fi
fi

# Activate virtual environment
source incrementum-env/bin/activate

# Run dependency check
echo "Checking dependencies..."
python3 fix_dependencies.py

# Check exit code
if [ $? -ne 0 ]; then
    echo "Failed to set up dependencies. Please check the error messages above."
    exit 1
fi

# Fix DOCX dependency specifically
echo "Fixing DOCX dependency..."
python3 fix_docx.py

# Check exit code
if [ $? -ne 0 ]; then
    echo "Failed to fix DOCX dependency. Please check the error messages above."
    exit 1
fi

# Initialize database if needed
if [ ! -f "$(python3 -c 'import appdirs; print(appdirs.user_data_dir("Incrementum", "Incrementum"))')/incrementum.db" ]; then
    echo "Initializing database..."
    python3 init_db.py
fi

# Run the application
echo "Starting Incrementum..."
python3.11 main.py
