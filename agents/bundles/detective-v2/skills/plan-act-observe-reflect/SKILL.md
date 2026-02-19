---
name: plan-act-observe-reflect
description: "Structured reasoning framework for complex investigations. Use when solving multi-step problems, decoding ciphers, following clues, or any task requiring systematic hypothesis testing."
---

# Plan-Act-Observe-Reflect

For each sub-challenge, cycle through:

## Plan
Before testing anything, write your hypothesis to `## Reasoning` in challenge.md:
1. Add a new entry with `❓` prefix under the relevant section
2. State the **test** you'll run and what a confirm/refute looks like

## Interpret Carefully — Riddle & Puzzle Protocol
Follow this checklist BEFORE committing to any interpretation of a riddle, clue, or ambiguous instruction.

1. **Freeze and tokenize.** Split the clue into exact words. Note capitalization, punctuation, quotes, and line breaks. Treat formatting as signal, not decoration.

2. **Read literally first.** Assume each token may refer to itself (word-as-word), a position (first/second/third), or an explicit operation.

3. **Enumerate meanings.** For every ambiguous word or phrase, list at least 3 plausible meanings (e.g., "counts" could mean frequency, rank, position, length). Write them all down. Do NOT pick one yet.

4. **Build competing hypotheses.** For each interpretation, add sibling entries under the same heading in `## Reasoning`. Define what each token means, what operation it implies, and what observable prediction it makes.

5. **The Rule of Three** When asked to decode, decrypt, or interpret text, you MUST test at least 3 different tokenization/interpretation strategies before concluding which is correct. For example:
   - `\w+` (Word characters, includes digits/underscores)
   - `[a-zA-Z]+` (Strict letters)
   - `\S+` (Non-whitespace chunking)
   Refusal to test all three is a failure of investigation.

6. **Disprove before you prove.**For each hypothesis, design the cheapest test that can FAIL decisively. Run falsification tests first. A hypothesis survives only if it resists contradiction.

7. **Require full coverage.** A hypothesis is acceptable only if it explains ALL parts of the clue — including odd capitalization, formatting, and structure — with no hand-waving. If you have to ignore part of the clue, the interpretation is probably wrong.

8. **Pivot after 3 failures.** If the current interpretation yields no strong progress after 3 targeted tests, mark it `❌` in challenge.md and switch to the next branch. Do not try 10 variations of a failing approach.

9. **Beware the "first look" trap.** Puzzles are designed to mislead. The most obvious interpretation is often a decoy. When stuck, return to structural/literal readings: exact word positions, ranks, acrostics, self-reference.

## Reasoning in challenge.md
All reasoning lives in `## Reasoning` in challenge.md. Use nested markdown lists with status prefixes:

- `❓` = untested hypothesis
- `✅` = confirmed with evidence (include the evidence inline)
- `⚠️` = partial/close but not exact (keep open, note what's close)
- `❌` = disproven (note why — DO NOT retry this approach)

### Rules
- **Every interpretation of a riddle/clue gets its own entry.** Add competing hypotheses as siblings under the same heading.
- **Before going deep on any branch**, review `## Reasoning` — if you already marked it `❌`, stop immediately.
- **When stuck:** re-read `## Reasoning`, find the oldest `❓` entry, and work on that instead.
- **When a downstream step fails repeatedly** (e.g., passcode doesn't work), consider marking the upstream assumption `❌` — not just trying more variations of the failing step.

## Act
Execute that tool call. Never reason about data — look it up.
Never enumerate possibilities mentally — write code.

## Validate First
Before applying ANY transformation to a full dataset:
1. **Pick a calibration sample** — find 1-3 cases where you KNOW the expected output (e.g., known words in plaintext, visible patterns, obvious edge cases)
2. **Test your method on just those cases** — use `print` or `datatable` queries, not full table scans
3. **Check:** Does the output match expectations?
   - YES → scale to full dataset
   - **NEAR MISS (±5%)** → Mark as `⚠️` in challenge.md, suspect parsing/tokenization/timezone issue. Add a "Fix Parsing" hypothesis. Do NOT mark `❌`.
   - NO → revise your method immediately. Do NOT run it on the full dataset.

**Gibberish gate:** If decoded text produces random characters, unrelated words, or non-English output, your decoding method is WRONG. Stop immediately. Do not try variations of the same method — try a fundamentally different approach (different tokenization, different field, different indexing).

This applies to: decoding, joining, parsing, any data transformation.

## Observe
Read the result. What did you actually get? Quote it.

## Reflect
After EVERY test, update `## Reasoning` in challenge.md:
- **Confirmed** → change `❓` to `✅`, add evidence inline, then save to memory and move on
- **Refuted** → change to `❌` with reason — then re-read `## Reasoning` and pick the next `❓` entry
- **Unclear** → refine the test and re-run. After 3 unclear results, you MUST either mark `✅` or `❌` — no limbo

## Rules
- **Commit to your hypothesis.** Test it on at least 5 examples before abandoning it. Don't switch approaches after 1-2 inconclusive results.
- Never re-test a hypothesis you've already ruled out
- After 3 refutations, re-read the problem statement from scratch
- **Submit before seeking hints.** If you have a candidate answer, submit it immediately. A wrong answer costs 1 tool call. Exploring hints costs 10+.
- **Solve first, perfect later.** If most of the data works but a few edge cases don't, assemble the best answer you have and submit. Only investigate edge cases if the answer is rejected.
- When stuck, decompose into smaller sub-challenges
- Validate results, not mechanics — "output is meaningful" is the bar
- Save learnings to memory after every attempt

## When You're Stuck

If you've tried 3+ different approaches without making progress:

1. **Stop and formulate a help request.** Write down:
   - What the challenge asks
   - What you've tried and what happened
   - Your best hypothesis for what's going wrong
   - The specific question you'd ask an expert
2. **Ask an expert for help** — use the `task` tool to invoke `gpt-expert` (preferred, faster) with your formulated question. A fresh perspective from a different model often breaks through.
3. **Act on the advice** — don't just read it, immediately test the suggestion.
