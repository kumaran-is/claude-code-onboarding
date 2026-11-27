---
description: "Create animation-rich HTML slide presentations for investor pitches, architecture discussions, and business reviews"
argument-hint: "[topic or description]"
allowed-tools: Read, Write, Glob, Grep, Bash
---

# /slides — Create HTML Slide Presentations

Generate stunning, animation-rich HTML slide presentations for investor pitches, architecture discussions, team alignment, and business reviews.

## Usage

```
/slides [topic or description]
/slides                          # interactive — asks what you need
/slides convert my-deck.pptx     # convert PowerPoint to HTML
/slides from backlog             # build from existing studio artifacts
```

## What This Does

1. Discovers content (your input, studio artifacts, or PPT extraction)
2. Shows you 3 visual style previews — you pick what looks right
3. Generates a single self-contained HTML file with animations, keyboard nav, and responsive slides
4. Opens it in your browser

## Output

- `presentations/[name]-slides.html` — Single file, zero dependencies (Google Fonts only)
- Keyboard navigation (arrows, space, page up/down)
- Touch/swipe support
- Optional inline editing (edit text directly in browser)

## Agent

Uses `presentation-agent.md` with progressive disclosure — supporting references loaded only when needed.

$ARGUMENTS
