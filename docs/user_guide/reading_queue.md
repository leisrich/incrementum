# Reading Queue

The Reading Queue is a central feature of Incrementum that helps you organize and prioritize your learning materials. This document explains the queue functionality, with special focus on the new "Incrementum Randomness" feature.

## Overview

The Reading Queue manages your reading materials by:

- Displaying documents that are due for review based on spaced repetition principles
- Allowing you to prioritize documents by setting their importance
- Providing various filtering and sorting options
- Scheduling documents for future reading based on your ratings

The queue makes use of an FSRS-inspired algorithm (Free Spaced Repetition Scheduler) to optimize when you should review documents, balancing:

- Document priority
- Document difficulty
- Time since last review
- Target retention rate

## Queue Interface

The Queue is accessible from the main window through:

- The "View Queue" button in the toolbar
- The "Tools → Reading Queue" menu option

The Queue View provides multiple ways to manage your reading materials:

- **Queue List**: Shows documents due for review, sorted by priority and due date
- **Calendar View**: Shows a day-by-day forecast of upcoming reviews
- **Category Tree**: Organizes documents by category for easy navigation

## Incrementum Randomness

### What is Incrementum Randomness?

Incrementum Randomness introduces serendipity and variety into your reading queue. While a traditional spaced repetition system is purely deterministic, showing documents in a fixed order based on scheduling algorithms, the randomness feature allows for discovery and unexpected connections between topics.

### Benefits of Randomness

Adding randomness to your queue can:

- Prevent monotony and boredom in your learning routine
- Help you discover connections between different topics
- Expose you to materials you might otherwise postpone indefinitely
- Make learning more fun and engaging
- Simulate how ideas naturally connect in real-world contexts

### How to Use the Randomness Slider

In the Queue View, you'll find a slider labeled "Incrementum Randomness" that allows you to adjust how much randomness and serendipity you want in your reading queue:

- **0% (Deterministic)**: The queue follows strict spaced repetition principles, showing documents in order of priority and due date.
- **50% (Balanced)**: The queue maintains spaced repetition principles while introducing moderate variety.
- **100% (Serendipitous)**: The queue emphasizes variety and discovery, while still considering document priorities.

Adjust the slider to your preferred level of randomness. Your setting will be saved and applied to future queue selections.

### How the Randomness Algorithm Works

The randomness algorithm employs different strategies based on the level set:

#### Low Randomness (1-50%)
- Mostly follows standard spaced repetition ordering
- Adds slight variations to the queue order
- Still prioritizes documents that are due today
- Introduces occasional "surprise" documents

#### Medium Randomness (51-80%)
- Balances scheduled items with variety
- Introduces documents from different categories
- Mixes due documents with new materials
- Considers document priority alongside random factors

#### High Randomness (81-100%)
- Focuses on serendipity and discovery
- Selects documents from underrepresented categories
- Introduces documents that haven't been seen in a long time
- Deliberately varies the topics you encounter
- Still maintains a small weight for priority

Your randomness setting is saved between sessions, so you only need to adjust it when you want to change your learning experience.

## Tips for Using the Reading Queue

- **Start with low randomness** when you're new to Incrementum to build familiarity with the spaced repetition system
- **Increase randomness** when you feel your learning has become too routine or predictable
- **Experiment with different settings** to find what works best for your learning style
- **Use high randomness** when exploring a new field to gain breadth before depth
- **Lower randomness** when preparing for exams or focusing on mastering specific topics

## Additional Queue Features

In addition to randomness, the queue provides these powerful features:

- **Document Prioritization**: Set priority levels (1-100) for documents
- **Category Filtering**: Focus on specific categories or topics
- **Tag Filtering**: Filter documents by tags
- **Rating System**: Rate documents after reading to inform the scheduling algorithm
- **Drag and Drop**: Manually reorder documents when needed
- **Search**: Find specific documents in your queue
- **Statistics**: Track your reading progress and schedule

Remember that the Queue is designed to optimize your learning while keeping it engaging and effective. The randomness feature adds an element of discovery to the precision of spaced repetition. 