---
description: "Apply review feedback to improve a wireframe using 3-pass iteration"
argument-hint: "[path to wireframe HTML file]"
allowed-tools: Read, Write, Edit, Glob, Grep
---

Use the **wireframe-iterator** agent to improve: $ARGUMENTS

If no file path is provided, find the most recently modified wireframe HTML file in the project directories (exclude index.html, sample/, .claude/, .github/).

If review feedback exists in the conversation, use it. Otherwise, ask the user what needs to be improved.
