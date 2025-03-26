from setuptools import setup, find_packages

setup(
    name="incrementum",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "sqlalchemy>=1.4.0",
        "PyQt6>=6.4.0",
        "PyQt6-WebEngine>=6.4.0",
        "spacy>=3.0.0",
        "nltk>=3.6.0",
        "scikit-learn>=0.24.0",
        "beautifulsoup4>=4.9.0",
        "requests>=2.25.0",
        "pdfminer.six>=20200726",
        "isodate"
    ]
) 