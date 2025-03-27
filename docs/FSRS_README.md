# FSRS Implementation in Incrementum

## Overview

Incrementum now uses the Free Spaced Repetition Scheduler (FSRS) algorithm to schedule both documents and learning items. FSRS is an advanced scheduling algorithm that improves retention by optimizing intervals between reviews.

## About FSRS

FSRS, developed by Jarrett "Phthonus" Ye, is a state-of-the-art spaced repetition algorithm that uses a neural network to model memory. Compared to older algorithms like SuperMemo's SM-2 and SM-18, FSRS has several advantages:

- **Better retention**: FSRS can achieve better retention with fewer reviews
- **Sophisticated memory model**: Uses memory stability and difficulty as key parameters
- **Adaptive difficulty**: Adjusts to each item's unique difficulty level
- **Efficient scheduling**: Avoids review clumping by spreading reviews optimally
- **Flexible rating system**: Uses a 4-point scale that maps intuitively to memory states

## Rating Scale

The FSRS rating scale consists of 4 points:

1. **Again** - You forgot the information completely or almost completely
2. **Hard** - You remembered with significant difficulty
3. **Good** - You remembered with some effort
4. **Easy** - You remembered easily with no hesitation

This scale replaces the old SM-18 0-5 scale. The application will automatically convert between scales as needed.

## Implementation Details

### For Document Reading

Documents are scheduled for review using FSRS principles based on:
- **Stability**: How well you remember the document's content (grows with each review)
- **Difficulty**: How challenging the document is to recall
- **Priority**: User-defined importance (higher priority = more frequent reviews)
- **Retrievability**: Target probability of remembering the document

### For Learning Items

Learning items (flashcards, cloze deletions, etc.) use the full FSRS algorithm with:
- **Optimized intervals**: Calculated based on memory model parameters
- **Difficulty adjustment**: Each item has its own difficulty level
- **Explicit stability tracking**: Memory stability is tracked and updated with each review
- **Priority weighting**: Important items can be reviewed more frequently

## Database Migration

A migration script (`migrations/fsrs_migration.py`) has been provided to update your database to support FSRS. This script:
1. Adds the required FSRS fields to the database tables
2. Migrates existing SM-18 data to FSRS format
3. Initializes FSRS parameters for existing items

Run this script before using the application:

```bash
python -m migrations.fsrs_migration
```

## Transitioning from SM-18

For backward compatibility, a transitional layer is provided that maps between the SM-18 and FSRS interfaces. This ensures that:
- Existing code continues to work without modification
- Review history and scheduling data is preserved
- The application can gradually transition to FSRS

## Algorithm Parameters

The default FSRS parameters are carefully tuned, but can be customized for advanced users. The parameters include:
- **w vector**: Weights of the model
- **D vector**: Difficulty vector for each rating
- **THETA**: Scaling factor for difficulty
- **R_TARGET**: Target retrievability (default: 0.9 or 90% retention)
- **Priority weights**: How much item priority affects scheduling

## Recent Enhancements

### Incrementum Randomness

Incrementum now features a randomness slider that allows users to introduce serendipity and variety into their reading queue. While traditional spaced repetition systems are purely deterministic, the Incrementum Randomness feature allows for discovery and unexpected connections between topics.

#### Randomness Levels

The randomness feature operates at three main levels:

- **Low Randomness (1-50%)**: Mostly follows standard spaced repetition ordering with slight variations.
- **Medium Randomness (51-80%)**: Balances scheduled items with variety, introducing documents from different categories.
- **High Randomness (81-100%)**: Focuses on serendipity and discovery, selecting documents from underrepresented categories and introducing materials not seen in a long time.

#### Benefits

Adding randomness to your queue can:
- Prevent monotony in your learning routine
- Help discover connections between different topics
- Expose you to materials you might otherwise postpone
- Make learning more engaging

#### How to Use

Adjust the "Incrementum Randomness" slider in the Queue View to set your preferred level of randomness. Your setting will be saved and applied to future queue selections.

For more information, see the [Reading Queue documentation](user_guide/reading_queue.md).

## References

- [FSRS4Anki](https://github.com/open-spaced-repetition/fsrs4anki/) - Original implementation
- [Memcode FSRS Documentation](https://fsrs.memcode.com/) - Detailed algorithm explanation
- [How to Build a Time Machine](https://www.youtube.com/watch?v=1r0_AZlGgGk) - Video explanation by the creator 