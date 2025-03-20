# Incrementum User Guide

## Introduction

Incrementum is an advanced incremental learning system designed to help you efficiently process and retain information. It combines document management, knowledge extraction, and spaced repetition techniques into a single integrated application.

This guide will walk you through setting up and using Incrementum to create your own personal knowledge base and optimize your learning.

## Table of Contents

1. [Installation](#installation)
2. [Getting Started](#getting-started)
3. [Importing Documents](#importing-documents)
4. [Extracting Knowledge](#extracting-knowledge)
5. [Creating Learning Items](#creating-learning-items)
6. [Reviewing with Spaced Repetition](#reviewing-with-spaced-repetition)
7. [Searching and Filtering](#searching-and-filtering)
8. [Knowledge Network](#knowledge-network)
9. [Tags and Organization](#tags-and-organization)
10. [Backup and Restore](#backup-and-restore)
11. [Settings and Customization](#settings-and-customization)
12. [Keyboard Shortcuts](#keyboard-shortcuts)
13. [Troubleshooting](#troubleshooting)

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- Qt libraries (for PyQt6)

### Install Steps

1. **Clone or download the repository**

```bash
git clone https://github.com/melpomenex/incrementum.git
cd incrementum
```

2. **Create a virtual environment**

```bash
python -m venv incrementum-env
```

3. **Activate the virtual environment**

On Linux/macOS:
```bash
source incrementum-env/bin/activate
```
On Windows run this command to get going quickly in Powershell:
```bash
.\setup.ps1
```
On Windows:
```bash
incrementum-env\Scripts\activate
```

4. **Install dependencies**

```bash
pip install -r requirements.txt
```

5. **Initialize the database**

```bash
python init_db.py
```

6. **Run the application**

```bash
python main.py
```

## Getting Started

When you first launch Incrementum, you'll see the home screen with quick access to common actions:

- **Import Document**: Start by importing PDF files, web pages, or other text documents
- **Start Review Session**: Begin reviewing due learning items
- **Search**: Search across your knowledge base
- **Statistics Dashboard**: View your learning progress

The left panel shows your document categories and a list of documents. The main area contains tabs for documents, extracts, learning items, and other views.

## Importing Documents

### Importing a Local File

1. Click the **Import File** button in the toolbar or go to **File > Import File**
2. Select a supported file type (PDF, HTML, TXT, EPUB, DOCX)
3. Choose the file from your computer
4. The document will be imported and processed automatically

### Importing from a URL

1. Click **File > Import from URL**
2. Enter the URL of the web page or online document
3. Click **OK** to import the content

After importing, the document will open in a new tab. PDF documents use the enhanced PDF viewer with highlighting and extraction capabilities.

## Extracting Knowledge

As you read through documents, you'll want to extract key information into your knowledge base:

### Creating Extracts from PDFs

1. Open a PDF document
2. Select text by dragging your mouse over content
3. Click the **Create Extract** button
4. The extract will be created and opened in a new tab

### Creating Extracts Manually

1. Go to **Edit > New Extract**
2. Select a source document
3. Enter the content in the editor
4. Set the priority (1-100) based on importance
5. Click **Save**

### Auto-Segmenting Documents

1. Open a document
2. Click the **Auto-Segment** button
3. The document will be analyzed and divided into logical segments as extracts
4. Review the generated extracts

## Creating Learning Items

Learning items are what you'll review with spaced repetition. They can be question-answer pairs or cloze deletions:

### Creating Items Manually

1. Open an extract
2. Click **Edit > New Learning Item** or use the extract's built-in item creator
3. Select the item type (Question-Answer or Cloze Deletion)
4. Enter the question and answer
5. Set the priority
6. Click **Save**

### Using AI-Assisted Generation

1. Open an extract
2. In the learning item editor, select "AI-assisted generation"
3. Choose the number of items to generate
4. Click **Generate Questions**
5. Review the suggestions and select ones to keep
6. Click **Save** or **Generate More**

## Reviewing with Spaced Repetition

Incrementum uses an advanced spaced repetition algorithm (based on SM-18) to optimize review timing:

### Starting a Review Session

1. Click the **Start Review Session** button or go to **Learning > Start Review Session**
2. You'll see your current due items
3. Rate your recall from 0-5:
   - 0: Complete blackout
   - 1: Incorrect response, but familiar
   - 2: Incorrect response, but easy recall
   - 3: Correct, but difficult
   - 4: Correct, after some hesitation
   - 5: Perfect recall
4. The algorithm will schedule the next review based on your performance

### Understanding the Review Schedule

- Items you know well will appear less frequently
- Difficult items will appear more often
- The system adapts to your learning curve
- You can view upcoming reviews in the **Statistics Dashboard**

## Searching and Filtering

Incrementum provides powerful search capabilities:

### Basic Search

1. Open the search panel via **View > Show Search Panel** or click **Tools > Search**
2. Enter your search terms
3. Select entity types to search (Documents, Extracts, Learning Items)
4. Results will appear in the tabs below

### Advanced Search Syntax

- Use quotes for exact phrases: `"neural networks"`
- Specify fields: `title:introduction author:smith`
- Exclude terms: `python NOT django`
- Use tag filters: `tag:science tag:biology`

### Filtering

Use the filter panels to narrow results by:
- Date ranges
- Priority levels
- Categories
- Tags
- Learning parameters (difficulty, interval, etc.)

## Knowledge Network

The Knowledge Network visualizes connections between your knowledge items:

### Viewing the Network

1. Go to **Tools > Knowledge Network**
2. Select the network type:
   - Document-Extract Network
   - Concept Network
   - Learning Path
3. Apply filters as needed
4. Explore connections by dragging nodes and hovering for details

### Creating Learning Paths

1. In the Knowledge Network view, select "Learning Path"
2. Enter a topic to create a path for
3. The system will generate a structured learning sequence
4. Follow the path for optimal learning progression

## Tags and Organization

Tags and categories help organize your knowledge base:

### Managing Categories

1. Right-click a category in the left panel
2. Select options to create, rename, or delete categories
3. Drag documents between categories

### Tagging Items

1. Right-click on a document or extract
2. Select **Edit Tags**
3. Enter tags separated by commas
4. Tags can be used for filtering and searching

### Auto-Tagging

1. Enable auto-tagging in **Settings > Document > Auto-suggest tags**
2. After importing or creating extracts, tags will be automatically suggested
3. Review and confirm the suggested tags

## Backup and Restore

Protect your knowledge base with regular backups:

### Creating Backups

1. Go to **Tools > Backup & Restore**
2. Select **Create Backup**
3. Choose whether to include document files
4. The backup will be created in your application data directory

### Restoring from Backup

1. Go to **Tools > Backup & Restore**
2. Select a backup from the list
3. Click **Restore Selected**
4. Confirm the restoration process

### Importing/Exporting Knowledge

1. Use **File > Export Knowledge Items** to share extracts or learning items
2. Use **File > Import Knowledge Items** to import items from another user
3. Select the appropriate format for sharing

## Settings and Customization

Customize Incrementum to suit your workflow:

### General Settings

1. Go to **Tools > Settings**
2. Adjust general options like auto-save interval and startup behavior

### User Interface

1. In Settings, go to the **User Interface** tab
2. Customize theme, font, and layout options

### Learning Algorithm

1. In Settings, go to the **Algorithm** tab
2. Fine-tune spaced repetition parameters
3. Adjust retention targets and interval modifiers

## Keyboard Shortcuts

Learn these shortcuts to speed up your workflow:

- **Ctrl+O**: Import file
- **Ctrl+R**: Start review session
- **Ctrl+F**: Search
- **Ctrl+Tab**: Switch between tabs
- **Ctrl+S**: Save current item
- **Ctrl+1-6**: Rate items during review (0-5)

## Troubleshooting

### Common Issues

**Q: The application won't start**
A: Check that you have activated the virtual environment and installed all dependencies.

**Q: PDF documents don't display correctly**
A: Ensure you have installed PyMuPDF correctly and your PDF is not corrupt.

**Q: Learning items aren't appearing in review**
A: Check that items have been created correctly and are due for review.

### Data Recovery

If you encounter database issues:
1. Go to **Tools > Backup & Restore**
2. Restore from the most recent backup
3. If no backup is available, check for the backup created before modifications in your data directory

### Getting Help

Visit the Incrementum GitHub repository for:
- Bug reporting
- Feature requests
- Community support
- Latest updates

---

## Example Workflows

### Research Paper Workflow

1. Import a research paper PDF
2. Read through and highlight key sections
3. Create extracts for methods, results, and conclusions
4. Generate learning items for important concepts and findings
5. Add appropriate tags (e.g., topic, field, author)
6. Review regularly to maintain retention

### Textbook Study Workflow

1. Import textbook chapters as separate documents
2. Create a category for the subject
3. Use auto-segmentation to extract key sections
4. Generate question-answer pairs for definitions and concepts
5. Create cloze deletions for formulas and processes
6. Schedule daily review sessions of new content
7. Use the Knowledge Network to visualize connections between concepts

### Language Learning Workflow

1. Import language texts and grammar explanations
2. Extract vocabulary and grammar rules
3. Create cloze deletions for sentence patterns
4. Generate question-answer pairs for vocabulary
5. Tag items by difficulty level and topic
6. Review daily with an emphasis on pronunciation
7. Track retention statistics to identify problem areas

---

Remember that incremental learning is a process - start small, focus on quality extracts, and maintain a consistent review schedule for best results.
# incrementum
# incrementum
