# Incrementum Installation and Setup Guide

This guide will walk you through the process of setting up Incrementum, an advanced incremental learning system, on your computer.

## System Requirements

- **Operating System**: Linux (preferred), macOS, or Windows
- **Python**: Version 3.8 or higher
- **Disk Space**: At least 500MB for the application and dependencies
- **Memory**: Minimum 4GB RAM (8GB or more recommended for large documents)
- **Additional Requirements**: Qt libraries for GUI (included in the installation process)

## Installation Steps

### 1. Install Python Dependencies

Before installing Incrementum, make sure you have the following prerequisites:

#### On Linux (Ubuntu/Debian):

```bash
# Install Python and pip
sudo apt update
sudo apt install python3 python3-pip python3-venv

# Install Qt dependencies
sudo apt install qt6-base-dev libgl1-mesa-dev

# Install other dependencies for PDF processing
sudo apt install libpoppler-dev poppler-utils tesseract-ocr
```

#### On macOS:

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python

# Install Qt dependencies
brew install qt@6

# Install other dependencies
brew install poppler tesseract
```

#### On Windows:

1. Download and install Python 3.8 or higher from [python.org](https://www.python.org/downloads/)
2. Make sure to check "Add Python to PATH" during installation
3. Install Microsoft Visual C++ Build Tools if needed

### 2. Set Up the Incrementum Repository

```bash
# Clone the repository
git clone https://github.com/melpomenex/incrementum.git
cd incrementum

# Create and activate a virtual environment
python -m venv incrementum-env

# On Linux/macOS
source incrementum-env/bin/activate

# On Windows
incrementum-env\Scripts\activate
```

### 3. Install Required Packages

```bash
# Install dependencies
pip install -r requirements.txt
```

The `requirements.txt` file includes all necessary Python packages:

```
PyQt6==6.5.0
SQLAlchemy==2.0.15
alembic==1.10.4
pdfminer.six==20221105
PyPDF2==3.0.1
beautifulsoup4==4.12.2
lxml==4.9.2
ebooklib==0.18
markdown==3.4.3
python-docx==0.8.11
nltk==3.8.1
scikit-learn==1.2.2
spacy==3.5.3
appdirs==1.4.4
python-dateutil==2.8.2
requests==2.30.0
pymupdf==1.22.3
pytesseract==0.3.10
matplotlib==3.7.1
networkx==3.1
pygraphviz==1.10
```

### 4. Download Additional Resources

Some components require additional resources:

```bash
# Download NLTK resources
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"

# Download spaCy language model
python -m spacy download en_core_web_sm
```

### 5. Initialize the Database

```bash
# Run the database initialization script
python init_db.py
```

This will create the SQLite database in your user data directory and set up initial categories.

### 6. Run Incrementum

```bash
# Launch the application
python main.py
```

## Folder Structure

After installation, your Incrementum folder should look like this:

```
incrementum/
├── assets/                # Application assets and resources
├── core/                  # Core application modules
│   ├── content_extractor/     # Knowledge extraction components
│   ├── document_processor/    # Document import and processing
│   ├── knowledge_base/        # Database and storage
│   ├── knowledge_network/     # Network visualization
│   ├── spaced_repetition/     # SM-18 implementation
│   └── utils/                 # Utility functions
├── models/                # Data models
├── ui/                    # User interface components
│   ├── models/                # UI data models
├── incrementum-env/       # Virtual environment (created during setup)
├── main.py                # Application entry point
├── init_db.py             # Database initialization
├── requirements.txt       # Dependencies list
└── README.md              # Project documentation
```

## Application Data Location

Incrementum stores your data in the following locations:

- **Linux**: `~/.local/share/Incrementum/Incrementum/`
- **macOS**: `~/Library/Application Support/Incrementum/Incrementum/`
- **Windows**: `C:\Users\USERNAME\AppData\Local\Incrementum\Incrementum\`

These folders contain:
- Your SQLite database
- Document files
- Backups
- Configuration files

## Troubleshooting Common Installation Issues

### Python Version Issues

If you encounter errors related to Python version:

```bash
# Check your Python version
python --version

# If it's below 3.8, install a newer version and update your virtual environment
```

### Missing Qt Dependencies

If you see errors related to PyQt:

```bash
# On Linux
sudo apt install python3-pyqt6

# On macOS
brew install pyqt@6

# On Windows, reinstall PyQt6 with pip
pip uninstall PyQt6
pip install PyQt6
```

### PDF Processing Issues

If PDF processing doesn't work correctly:

```bash
# Ensure poppler and related tools are installed
# On Linux
sudo apt install poppler-utils

# On macOS
brew install poppler

# Check PyMuPDF installation
pip uninstall pymupdf
pip install pymupdf==1.22.3
```

### Database Initialization Failure

If the database fails to initialize:

1. Check permissions in your user data directory
2. Delete any existing incrementum.db file and retry
3. Make sure SQLAlchemy is installed correctly

## Post-Installation Configuration

### First-time Setup

When you first run Incrementum, you may want to configure:

1. **Settings**: Go to Tools > Settings
   - Set your default document directory
   - Configure auto-saving interval
   - Choose your preferred theme
   - Adjust spaced repetition parameters

2. **Create Categories**: Right-click in the category panel to create your organizational structure
   - Create subject categories
   - Add subcategories for specific topics

3. **Import Sample Documents**: Use File > Import File to add your first documents
   - Try starting with a PDF document
   - Experiment with extraction and learning item creation

### Optional Components

For advanced features, you might want to install:

- **GraphViz**: For enhanced knowledge network visualization
  ```bash
  # Linux
  sudo apt install graphviz
  
  # macOS
  brew install graphviz
  
  # Windows - download from graphviz.org
  ```

- **Tesseract OCR**: For processing scanned documents
  ```bash
  # Linux
  sudo apt install tesseract-ocr
  
  # macOS
  brew install tesseract
  
  # Windows - download from github.com/UB-Mannheim/tesseract/wiki
  ```

## Upgrading

To upgrade Incrementum to a newer version:

```bash
# Navigate to your Incrementum directory
cd path/to/incrementum

# Activate the virtual environment
source incrementum-env/bin/activate  # On Linux/macOS
incrementum-env\Scripts\activate     # On Windows

# Pull the latest changes
git pull

# Update dependencies
pip install -r requirements.txt

# Run any database migrations
python -m alembic upgrade head
```

Always backup your data before upgrading by using the built-in backup feature (Tools > Backup & Restore).

## Running Incrementum in Development Mode

If you're a developer or want to modify Incrementum:

```bash
# Enable debug logging
python main.py --debug

# Run with specific settings file
python main.py --settings-file=custom_settings.json
```

---

## Getting Help

If you encounter issues with installation or setup:

1. Check the troubleshooting section of this guide
2. Review the full documentation
3. Check the GitHub repository issues section
4. Join the community forum for support

For bug reports or feature requests, please visit the GitHub repository.

---

Now that you have successfully installed Incrementum, refer to the User Guide for instructions on how to use the application effectively.
