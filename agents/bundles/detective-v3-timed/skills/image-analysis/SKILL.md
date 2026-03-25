---
name: image-analysis
description: "Iterative image analysis protocol for extracting hidden clues from screenshots, diagrams, and artwork images."
---

# Image Analysis — Iterative Protocol

When you take a screenshot or are presented with an image, follow this structured process. Write all findings to challenge.md.

## Step 1: Describe
Describe the overall scene in one sentence, then describe every visible element in detail: objects, text, letters, symbols, colors, positions, and spatial relationships.

## Step 2: Locate letter regions and crop each one
Identify the bounding box of each area containing a letter. Use Python with PIL to crop each letter into a separate image file:

```python
from PIL import Image

img = Image.open("screenshot.png")

# List approximate bounding boxes: (x1, y1, x2, y2) for each letter region
regions = [
    (310, 140, 340, 170),  # region 1
    (340, 140, 370, 170),  # region 2
    (370, 140, 400, 170),  # region 3
]

for i, (x1, y1, x2, y2) in enumerate(regions):
    crop = img.crop((x1, y1, x2, y2))
    path = f"letter_{i}.png"
    crop.save(path)
    print(f"Saved {path} ({x2-x1}x{y2-y1}px)")
```

Make each crop generous (add ~10px padding around the letter) so the character is clearly visible.

## Step 3: Identify each letter using subagents
For each cropped letter image, ask a subagent to identify the single character:

```
For each letter_N.png, call a subagent (task tool) with:
  prompt: "This image contains a single letter or character. What letter is it? Reply with ONLY the letter."
  attachment: letter_N.png
```

Collect the identified letters along with the (x, y) center of each crop region.

## Step 4: Apply spatial reading algorithms
Use Python to programmatically try different reading orders on the identified letters:
Use Python to programmatically try different reading orders on the cataloged letters. Write and run a script that:

```python
import math

# Paste your cataloged letters here
letters = [
    ("Y", 320, 150),
    ("E", 350, 150),
    ("S", 380, 150),
]

# Calculate center of all points
cx = sum(x for _, x, _ in letters) / len(letters)
cy = sum(y for _, _, y in letters) / len(letters)

# Sort by different spatial algorithms
def by_left_to_right(item): return (item[1], item[2])
def by_right_to_left(item): return (-item[1], item[2])
def by_top_to_bottom(item): return (item[2], item[1])
def by_clockwise(item):
    angle = math.atan2(item[2] - cy, item[1] - cx)
    return angle
def by_counter_clockwise(item):
    angle = math.atan2(item[2] - cy, item[1] - cx)
    return -angle
def by_distance_from_center(item):
    return math.sqrt((item[1] - cx)**2 + (item[2] - cy)**2)

algorithms = {
    "left-to-right": by_left_to_right,
    "right-to-left": by_right_to_left,
    "top-to-bottom": by_top_to_bottom,
    "clockwise": by_clockwise,
    "counter-clockwise": by_counter_clockwise,
    "spiral-outward": by_distance_from_center,
}

for name, key_fn in algorithms.items():
    sorted_letters = sorted(letters, key=key_fn)
    word = "".join(ch for ch, _, _ in sorted_letters)
    print(f"{name}: {word}")
```

**CRITICAL: Use ALL letters.** Do NOT filter, deduplicate, or subset the letters before running the algorithms. Every cataloged letter participates in every ordering. The goal is to produce every possible spatial reading — only AFTER seeing all outputs should you reason about which ones form words.

Review the output — does any reading order produce a recognizable word, name, or phrase?

## Step 5: Connect to clues
Re-examine the results through the lens of your current challenge. Only NOW should you reason about which output makes sense. Do not pre-filter letters based on assumptions about word length, duplicates, or expected answers.

## When to use this protocol
- After taking any screenshot during a puzzle
- When viewing artwork images referenced by a challenge
- When a login page, diagram, or visual clue appears
- Any time an image might contain hidden text, symbols, or patterns

## Key principle
In puzzles, the answer is often hidden in plain sight within an image. A quick glance will miss it. The catalog step forces you to enumerate every element with coordinates, and the algorithm step forces you to systematically try every reading order instead of guessing.
