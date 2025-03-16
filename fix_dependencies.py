# Create a simple shim script to handle missing dependencies
# Save as "fix_dependencies.py"

import os
import sys
import logging
import importlib.util

def check_and_install_dependencies():
    """Check for required dependencies and install if needed."""
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger("dependency_check")
    
    # List of required packages
    required_packages = [
        "PyQt6",
        "PyQt6-WebEngine",  # For network visualization
        "SQLAlchemy",
        "pdfminer.six",
        "PyPDF2",
        "PyMuPDF",  # fitz
        "beautifulsoup4",
        "lxml",
        "nltk",
        "scikit-learn",
        "spacy",
        "appdirs",
        "humanize"
    ]
    
    missing_packages = []
    
    # Check for each package
    for package in required_packages:
        try:
            # Try to import the package
            if package == "PyQt6-WebEngine":
                # Special case for WebEngine
                spec = importlib.util.find_spec("PyQt6.QtWebEngineWidgets")
                if spec is None:
                    missing_packages.append(package)
            else:
                # Normal case
                spec = importlib.util.find_spec(package.split('.')[0])
                if spec is None:
                    missing_packages.append(package)
        except ImportError:
            missing_packages.append(package)
    
    # If there are missing packages, attempt to install them
    if missing_packages:
        logger.info(f"Missing packages: {', '.join(missing_packages)}")
        
        try:
            import subprocess
            
            # Check if pip is available
            try:
                subprocess.run([sys.executable, "-m", "pip", "--version"], 
                               check=True, capture_output=True)
            except (subprocess.SubprocessError, FileNotFoundError):
                logger.error("Pip is not available. Please install pip and try again.")
                return False
            
            # Install missing packages
            for package in missing_packages:
                logger.info(f"Installing {package}...")
                
                try:
                    subprocess.run([sys.executable, "-m", "pip", "install", package], 
                                  check=True, capture_output=True)
                    logger.info(f"Successfully installed {package}")
                except subprocess.SubprocessError as e:
                    logger.error(f"Failed to install {package}: {e}")
                    return False
            
            # Special case for NLTK data
            try:
                import nltk
                nltk.download('punkt', quiet=True)
                nltk.download('stopwords', quiet=True)
                nltk.download('wordnet', quiet=True)
                logger.info("Successfully downloaded NLTK data")
            except Exception as e:
                logger.warning(f"Failed to download NLTK data: {e}")
                logger.warning("Some NLP features may not work correctly")
            
            # Special case for spaCy model
            try:
                subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"], 
                              check=True, capture_output=True)
                logger.info("Successfully downloaded spaCy model")
            except subprocess.SubprocessError as e:
                logger.warning(f"Failed to download spaCy model: {e}")
                logger.warning("Some NLP features may not work correctly")
            
            return True
            
        except Exception as e:
            logger.error(f"Error installing dependencies: {e}")
            return False
    
    logger.info("All dependencies are satisfied")
    return True

def create_directory_structure():
    """Create the necessary directory structure."""
    
    logger = logging.getLogger("directory_check")
    
    # Core directories
    dirs = [
        "core",
        "core/document_processor",
        "core/document_processor/handlers",
        "core/content_extractor",
        "core/knowledge_base",
        "core/knowledge_network",
        "core/spaced_repetition",
        "core/utils",
        "ui",
        "ui/models",
        "assets"
    ]
    
    # Create directories if they don't exist
    for directory in dirs:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
                logger.info(f"Created directory: {directory}")
            except OSError as e:
                logger.error(f"Failed to create directory {directory}: {e}")
    
    # Create __init__.py files
    for directory in dirs:
        init_file = os.path.join(directory, "__init__.py")
        if not os.path.exists(init_file):
            try:
                with open(init_file, 'w') as f:
                    f.write("# Auto-generated __init__.py\n")
                logger.info(f"Created file: {init_file}")
            except OSError as e:
                logger.error(f"Failed to create file {init_file}: {e}")
    
    return True

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger("fix_dependencies")
    
    logger.info("Checking and installing dependencies...")
    deps_ok = check_and_install_dependencies()
    
    logger.info("Creating directory structure...")
    dirs_ok = create_directory_structure()
    
    if deps_ok and dirs_ok:
        logger.info("Setup completed successfully")
    else:
        logger.error("Setup completed with errors")
