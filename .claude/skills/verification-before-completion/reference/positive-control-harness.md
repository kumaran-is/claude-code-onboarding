# Positive-control harness: copy it, never rewrite it from memory

A positive control breaks the thing on purpose, confirms the test or gate goes **RED** for the right reason, then reverts. A test that has never been seen red is not evidence that it pins anything. This applies to your own fix and equally to a fix a reviewer suggested: a suggestion is a hypothesis until a control fires.

The rule that requires controls lives in `.claude/rules/verification-and-reporting.md` ("Action Claims Require Evidence") and, for hooks and gates, `.claude/rules/hook-and-gate-authoring.md`. This file is the reusable harness and the pitfalls that make hand-written controls lie. Copy the harness and extend it. Each guard in it exists because a control without it reported a false result.

## The harness (Python, works for any test runner)

```python
"""Positive controls for <change>.

Each mutation is inert but still compiles, is asserted to have reached disk before
the run, and is reverted in `finally`, so one failure cannot contaminate the next control.
"""
import os, pathlib, re, subprocess, sys, tempfile

ROOT = pathlib.Path("<repo root>")
# (name, file, anchor, inert mutation, command, regex the failure output must match)
CASES = [
    ("<what this proves>", ROOT / "<file>", "<anchor>", "<mutation>",
     ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", "<test>"], r"<expected failure>"),
]

env = {**os.environ, "PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}  # never write .pyc into the tree
failures = []
for name, path, old, new, cmd, want in CASES:
    original = path.read_text()
    # GUARD 1: the anchor is non-empty and occurs exactly once, counted as a literal substring.
    if not old or original.count(old) != 1:
        print(f"[BAD ANCHOR] {name}: {original.count(old) if old else 'empty'}"); failures.append(name); continue
    mutated = original.replace(old, new, 1)
    assert mutated != original, "replacement was a no-op"
    try:
        path.write_text(mutated)
        # GUARD 2: the mutation reached disk (count `new`, never `old not in` - see pitfalls).
        assert path.read_text().count(new) >= 1, "mutation did not reach disk"
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
    finally:
        # GUARD 3: always restore, and prove it.
        path.write_text(original)
        assert path.read_text() == original, f"RESTORE FAILED for {path}"
    out = proc.stdout + proc.stderr
    # GUARD 4: a run that could not build, collect or run any test is not a RED for our reason.
    broken = re.search(r"(?i)error during collection|no tests ran|compilation error|SyntaxError|ImportError", out)
    # GUARD 5: assert on CONTENT, not only on the exit status (a crash also exits non-zero).
    red = proc.returncode != 0 and not broken and re.search(want, out)
    print(f"[{'RED - control works' if red else 'NOT A VALID RED'}] {name}")
    if not red:
        failures.append(name)

print(f"controls that failed to fire: {len(failures)}")
sys.exit(1 if failures else 0)
```

Adapt the `broken` pattern to the runner: Vitest/Jest (`Failed to load`, `No test files found`), `flutter test` (`Error: ` compile output, `No tests ran`), JUnit (`COMPILATION ERROR`).

## Pitfalls (each one has produced a false result in practice)

| Pitfall | Symptom | Guard |
|---|---|---|
| Anchor not unique | The edit lands somewhere unintended | `count(old) == 1` |
| Multi-line anchor counted with `grep -cF` | A two-line anchor that occurs once reports 2 or 3 | `grep -F` treats each line as a separate pattern. Count with a literal substring count in a script, never `grep -cF` |
| Empty anchor | `"" in s` is always true. `replace("", x)` inserts at byte 0 | Reject empty anchors |
| Deletion as the mutation | Deleting an `except`/`catch` orphans its `try`. Swapping in an unimported symbol turns "RED" into a load error | Mutate to something **inert that still compiles**: flip a comparison, return the unguarded value, replace a predicate with `True` |
| Post-condition that cannot hold | When the mutation wraps the original, `old` is still a substring of `new`, so `old not in after` fails after the write and the restore never runs | Assert `after.count(new)`, and restore in `finally` |
| Mutation never reaches the artefact under test | An annotation or schema change needs codegen, so the control comes back GREEN and invites you to delete a good test | Run codegen inside the loop, and grep the generated file for the mutation |
| Absence-shaped control passes vacuously | The control asserts "no output", and gets none because the code crashed, not because the guard worked | Assert the reason too: stderr is empty and a test result was produced (see below) |
| Expected failure text too narrow | The control fires but is scored NOT A VALID RED | A broken guard can fail differently per platform or shell version (for example `unbound variable` under `set -u` on bash 3.2). Match every valid symptom with a regex alternation |
| Stale Python bytecode | A later in-tree run fails or passes against a clean `git diff`: the `.pyc` was written while the mutation was live, and a same-size edit restored within one second leaves mtime and size unchanged | Run controls with `PYTHONPYCACHEPREFIX=$(mktemp -d)` and `-p no:cacheprovider`. If a stale `.pyc` already exists, delete that one file |
| A control that does not fire | "So the code must be fine" | It is a finding about the **test**: it pins nothing, or the layer you mutated is not the layer the test observes. Move the mutation one layer closer and run again |

## The absence trap

The hardest control to get right asserts that something does **not** happen: "no request is sent", "the scan returns nothing", "the question is not asked again". Absence has many causes, and only one of them is the guarantee you want.

```python
# Wrong: passes when the guard works AND when the function crashed
out = run(...)
assert out == ""

# Right: tells the two causes apart
out, err, code = run_capturing(...)
assert out == ""     # nothing was produced...
assert err == ""     # ...and not because it blew up
assert code == 0
```

The same applies to scanners and gates: zero findings means nothing until the same scan, pointed at a planted violation, reports it (`hook-and-gate-authoring.md`).

## When a control is not required

A change with nothing executable to break (a comment, docs, a pure rename) needs no control. Say so, with the reason, instead of inventing a control that proves nothing. When the claim is environmental ("no deployed revision still uses the old key"), run the command that settles it and paste its output. A file grep proves nothing there.
