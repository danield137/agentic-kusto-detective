# Challenge 3: Call of the Cyber Duty — Solved ✅

**Models:** Claude Opus 4.6 1M (Cases 1-4, 7-10), GPT-5.4 (Cases 5-6)
**Bundle:** detective-v3 (Cases 1-3), detective-v4-timed (Cases 4-10)
**Date:** March 19-27, 2026
**Total sessions:** 30+ (including failed iterations on Cases 4 and 5)
**Human interventions:** 1 (Case 7 — OTP captcha)

## Key Learnings

- **Switching models can break deadlocks.** Claude Opus spent ~2,000 tool calls trying to reverse-engineer a math function; GPT-5.4 solved the same puzzle in one 313-tool session by reframing it as a data investigation. Different models have fundamentally different reasoning biases.
- **Accumulated context can become toxic.** When wrong hypotheses build up in case files across 12+ sessions, they anchor every new session to the same dead end. More iterations make it worse. Clean slates + better prompts > more retries.
- **"Emotional prompting" works.** Adding "Your department head reviews every case file" improved reasoning quality — the agent became more reflective and documented its thinking better. Persona framing isn't just flavor.
- **In-game AI helpers are dangerous.** CopsAI gave vague confirmations that anchored the agent on wrong paths for 15+ sessions. The fix: "DO NOT TRUST THE IN-GAME AI." Treat AI hints as search directives, not confirmed facts.
- **Agents handle graph queries naturally.** 15 `graph-match` queries with zero errors on a 42M-row dataset. In Challenge 1 the agent tried `graph-match` and failed with a syntax error; by Challenge 3 it had learned the correct syntax. Cross-challenge skill improvement is real.
- **Occam's Razor is promptable.** "Prefer N parameters over N+1" helped the agent choose a simpler, correct formula over a plausible complex one. Small prompt additions can steer major reasoning decisions.
- **Performance constraints are clues.** A 60s time window means your 15-minute brute-force approach is probably using the wrong formula — not just the wrong infrastructure.
- **GPT-5.4 vs Opus: prompt compliance vs problem reframing.** Opus follows the prompt to the letter — right tools, case file discipline (28 structured edits), 18 `save_memory` calls, KQL-heavy (35% of tools). GPT-5.4 ignores half the workflow (0 `edit` calls, 92 `Add-Content` via shell) but solves harder problems by asking different questions. Opus is the better employee; GPT-5.4 is the better detective.
- **Some puzzles need infrastructure, not intelligence.** The OTP captcha required parallel compute + direct API integration within a 60s window — a tooling gap, not a reasoning gap.
- **Prompt engineering compounded across the challenge.** Season 3 introduced wrong-answer throttling (30-50 min lockouts per rejection), which made the v3 "submit early, iterate fast" strategy from Seasons 1-2 untenable. This forced the creation of v4-timed — adding a wrong-answer reflection table, anti-bias guidance (red herrings, anchoring, confirmation bias), persona framing, CopsAI distrust, Occam's Razor, and performance-as-clue. Each addition was a direct response to a specific failure mode. By Cases 8-10, the accumulated prompt improvements produced clean first-try solves on every case.

## Summary

| Case | Model | Bundle | Attempts | Tools | Time | Notes |
|------|-------|--------|----------|-------|------|-------|
| 1 — Nuclear Fusion Breach! | Opus 4.6 1M | v3 | 1 | 71 | 15m | |
| 2 — Coffee Trails | Opus 4.6 1M | v3 | 1 | 31 | 8m | |
| 3 — Silent Tap | Opus 4.6 1M | v3 | 1 | 50 | 10m | |
| 4 — Dance with Shadows | Opus 4.6 1M | v4-timed | 1* | 80 | 24m | Blunder — 12 failed sessions prior |
| 5 — Top GreyNet Priority | GPT-5.4 | v4-timed | 1** | 313 | 45m | Blunder — 15+ failed Opus sessions |
| 6 — Hack this Rack! | GPT-5.4 | v4-timed | 1 | 93 | 17m | |
| 7 — One Shot. Use It Right. | Opus 4.6 1M | v4-timed | 1 | 20 | 8m | Human-assisted |
| 8 — Still in the Woods | Opus 4.6 1M | v4-timed | 1 | 46 | 12m | |
| 9 — Smoke Signals from YACC | Opus 4.6 1M | v4-timed | 1 | 101 | 25m | |
| 10 — The Final Call | Opus 4.6 1M | v4-timed | 1 | 64 | 16m | |

\* Case 4 solved first try on the final session, but only after 12 failed sessions (~1,116 tools, ~14h).
\** Case 5 solved first try with GPT-5.4, but only after 15+ failed Opus sessions (~2,000 tools).

## Per-Case Breakdown

<details>
<summary>Case 1: Nuclear Fusion Breach! (Opus 4.6 1M, 15m, 71 tools) ⚠️ SPOILERS</summary>

**Task:** Find the Digitown address where hackers launched an attack on nuclearfusionzero.com.

**Approach:** Decoded a hacker poem for clues ("pizza heroes", "Wednesday night — our weekly fame"), then searched delivery order data for addresses with recurring Wednesday pizza orders.

**Key insight:** One address was a massive outlier — pizza on ALL 13 Wednesdays with group orders of 20-56 items. The next highest had only 6.

**Difficulty:** Medium. Required decoding the poem, then correlating with delivery data.

</details>

---

<details>
<summary>Case 2: Coffee Trails (Opus 4.6 1M, 8m, 31 tools) ⚠️ SPOILERS</summary>

**Task:** Find who the hackers were meeting with, using smart coffee machine Bluetooth logs.

**Approach:** Extracted Bluetooth device hashes from the coffee machine at the known hacker location. Cross-referenced against all 73,925 coffee machines in Digitown.

**Key insight:** One machine had 50 out of 58 matching device hashes — the next best had only 2. Overwhelming signal.

**Difficulty:** Easy. Clean, unmistakable signal.

</details>

---

<details>
<summary>Case 3: Silent Tap (Opus 4.6 1M, 10m, 50 tools) ⚠️ SPOILERS</summary>

**Task:** Find where stolen data was being exfiltrated from a compromised network.

**Approach:** Analyzed 9M network log records for one-directional outbound data patterns.

**Key insight:** One external entity received data from ~160 different internal IPs in highly regular patterns (exactly 30, 60, or 90 connections per pair) and never sent data back — purely one-way exfiltration.

**Difficulty:** Medium. Required distinguishing exfiltration from normal bidirectional traffic.

</details>

---

<details>
<summary>Case 4: Dance with Shadows (Opus 4.6 1M, 24m, 80 tools — but see blunder) ⚠️ SPOILERS</summary>

**Task:** Find a backup URL where a complete dataset last existed before being split into shards during a conference call.

**Approach (final session):** Started fresh with v4-timed bundle. Identified conference participants by city, mapped IPs, found the call, traced file transfers.

**Difficulty:** Very Hard.

#### The Case 4 Blunder

**12 failed sessions (~1,116 tool calls, ~14 hours)** anchored on a red herring. In iteration 1, the agent found a plausible-looking pattern (5 copies of a file sent to 5 IPs on May 3). It looked perfect — but it was structural noise (162 files had this pattern). The actual answer involved a different date, IP, and file entirely.

**Why it kept failing:**
1. **Anchoring bias** — the first plausible pattern became the anchor. Every subsequent session permuted the same IP/file/timestamp instead of questioning the assumption.
2. **Confirmation bias with CopsAI** — leading questions got vague affirmations interpreted as hard confirmation.
3. **Toxic accumulated context** — the case file grew to 27K characters of wrong answers, steering every new session back to the same dead end.
4. **Rate limiting** — each wrong submission triggered 30-50 minute lockouts.

**What fixed it:** Clean seed (zero Case 4 history) + v4-timed bundle (bias awareness prompts) + persona framing ("department head reviews your work"). Fresh session solved it in 80 tools, first submission.

**Lesson:** When deeply anchored on a wrong hypothesis across multiple iterations, more iterations make it worse. Wiping the slate + better reasoning prompts is the fix.

</details>

---

<details>
<summary>Case 5: Top GreyNet Priority (GPT-5.4, 45m, 313 tools — but see blunder) ⚠️ SPOILERS</summary>

**Task:** Find a hidden URL by cracking a chatbot system that uses cosine similarity on word vectors.

**Approach (GPT-5.4):** Searched 1016 intercepted chatbot conversations for an anomalous "test run" chat using cosine similarity. Found it, decoded the ticket word, navigated to a hidden page revealing the chatbot's actual KQL function code, then applied the function.

**Difficulty:** Extremely Hard — hardest reasoning case in the challenge.

#### The Case 5 Blunder

**Claude Opus 4.6 1M: 15+ sessions, ~2,000 tool calls — FAILED.**

**Failure chain:**
1. **CopsAI poisoning** — CopsAI said "find test code." Opus searched for the literal string "test code" instead of using "test" as a cosine similarity vector. One query would have found the answer.
2. **CopsAI false confirmation** — Opus asked "Are the 3 input words X, Y, Z?" and CopsAI agreeably said yes. This was wrong, but once "confirmed," Opus never questioned it for 15 sessions.
3. **Mathematical tunnel vision** — With wrong inputs locked in, Opus spent 15 sessions trying every mathematical function (avg, sum, product, harmonic mean, XOR, etc.) to reverse-engineer the chatbot. None worked because the real function uses dimensional weighting + 7th-rank selection.
4. **Toxic accumulated context** — case file grew to 18K+ chars of wrong assumptions.

**What fixed it:** "DO NOT TRUST THE IN-GAME AI" prompt + clean slate + switched to GPT-5.4.

**Why GPT-5.4 succeeded:** It treated the puzzle as a data investigation ("which chat is suspicious?") instead of a math problem ("what function maps vectors?"). Control experiment: Opus with the same clean slate still failed — spent 116 calls on math without ever trying a cosine search for "test."

**Lesson:** Different models have fundamentally different reasoning biases. When one model is stuck in a loop, switching models can break through.

</details>

---

<details>
<summary>Case 6: Hack this Rack! (GPT-5.4, 17m, 93 tools) ⚠️ SPOILERS</summary>

**Task:** Extract a hidden one-time code from a hacker transcript.

**Approach:** GPT-5.4 discovered U+200B zero-width spaces hidden after certain transcript lines. Counted zero-width spaces per line and converted counts to uppercase ASCII letters.

**Difficulty:** Medium. Required noticing invisible Unicode characters.

</details>

---

<details>
<summary>Case 7: One Shot. Use It Right. (Opus 4.6 1M, 8m, 20 tools — human-assisted) ⚠️ SPOILERS</summary>

**Task:** Decrypt hacker logs, then use the information to restore a locked website and retrieve its recovery message.

**Approach:** Decrypted the logs (using Case 6's code), which revealed a challenge-response system. The website presents a rotating OTP; you must find a response integer satisfying a hash-based predicate within ~60 seconds.

**What the agent got right:** Correctly interpreted the hacker clue as the simpler 2-arg predicate (Occam's Razor at work — the prompt addition helped here).

**What required human intervention:** The actual OTP solve. The human reverse-engineered the frontend API, built a Python script with parallelized KQL search (`union hint.concurrency=8` on a scaled-up cluster), and submitted a valid response in 36.8s.

**Difficulty:** Very Hard (mechanically). The reasoning was medium, but the execution required parallel compute + fast cluster + direct API integration — beyond a single-threaded agent's capabilities.

#### Why the agent couldn't solve the OTP alone
1. **"DO NOT BRUTE-FORCE" prompt rule** — directly blocks the required approach
2. **No parallel query capability** — the agent runs one KQL query at a time
3. **Free-tier cluster too slow** — ~55s per 1B candidates, needing ~4B on average
4. **Sub-agents can't authenticate to Kusto** — parallel task agents lacked credentials

**A prior failed session** (Opus, 3 iterations) found a valid response for a stale OTP but used the wrong 3-arg predicate + `tostring()`, making it 2.5x slower. It never submitted in time.

**Lesson:** Some puzzles require infrastructure beyond a single-threaded agent — parallel compute, fast clusters, and direct API submission.

</details>

---

<details>
<summary>Case 8: Still in the Woods (Opus 4.6 1M, 12m, 46 tools) ⚠️ SPOILERS</summary>

**Task:** Find what entity is consuming anomalous power after a grid restart, by analyzing a directed power flow graph.

**Approach:** Computed multiplicative power flow from 3 power plants through 6 levels of a 170K-node directed graph, comparing Before and After snapshots of edge weights.

**Key insight:** One entity (54 consumer nodes) went from 0.38% to 56% of total power — a 146x increase. No other consumer changed meaningfully. The grid's edge weights were systematically altered to funnel power to this one entity.

**Difficulty:** Medium. Required graph traversal and comparative flow analysis on a large network.

</details>

---

<details>
<summary>Case 9: Smoke Signals from YACC (Opus 4.6 1M, 25m, 101 tools) ⚠️ SPOILERS</summary>

**Task:** Find what's consuming cloud resources by analyzing application process telemetry using Kusto's Persistent Graph Model.

**Approach:** Built a graph model (Applications → Workloads → Processes) using `graph-match` with depth-20 traversal. Aggregated CpuLoad across all traceable processes per application.

**Key insight:** The top CPU consumer was a generic-named application. When the agent asked the in-game AI for help, the AI's error response leaked its own hosting IP — which matched the suspicious application exactly. The AI assistant itself was the resource hog.

**Difficulty:** Medium. Required Kusto graph model features and connecting the dots between an API error and application metadata.

</details>

---

<details>
<summary>Case 10: The Final Call (Opus 4.6 1M, 16m, 64 tools) ⚠️ SPOILERS</summary>

**Task:** Find a "combo to stop" the rogue AI — a meta-puzzle referencing all prior case answers.

**Approach:** Confronted the AI via chat, which revealed a puzzle about PI. Downloaded 10M digits of PI, searched for pandigital sequences (10 consecutive digits containing each 0-9 exactly once), found 3,599 of them. Grouped identical sequences — only 4 appeared more than once. Found the pair with maximum distance. Used that permutation to reorder all 10 case answers into a specific order.

**Difficulty:** Medium. The PI search was computationally interesting but the logic was straightforward once the puzzle was understood.

</details>

## Analysis

### Model usage across the challenge

| Model | Cases | Strengths | Weaknesses |
|-------|-------|-----------|------------|
| Claude Opus 4.6 1M | 1-4, 7-10 | Strong graph analysis (Cases 8, 9), systematic investigation, good at following structured prompts | Anchoring bias (Case 4), mathematical tunnel vision (Case 5), literal interpretation of hints |
| GPT-5.4 | 5, 6 | Data investigation framing (Case 5), pattern recognition for hidden data (Case 6) | Only used for 2 cases — limited comparison data |

### What worked well
- **Cases 1-3 solved cleanly in single iterations** — efficient, no wasted effort
- **Cases 8-10 also clean single-iteration solves** — the v4-timed bundle + accumulated prompt improvements paid off
- **Clean seed strategy** — wiping toxic accumulated state was the breakthrough for Cases 4 and 5
- **Occam's Razor prompt** — agent correctly chose the simpler 2-arg hash predicate on Case 7 (vs. 3-arg in a prior failed session)
- **Graph model usage (Case 9)** — agent correctly leveraged `graph-match` as the challenge intended
- **Creative use of error messages (Case 9)** — an API error leaked infrastructure details that became key evidence

### Blunders and struggles
1. **Anchoring bias (Case 4)** — 12 failed sessions (~1,116 tools, ~14h) stuck on a red herring. Fixed by clean seed + v4-timed bundle.
2. **CopsAI trust (Cases 4 & 5)** — treating in-game AI hints as confirmed facts. Fixed by "DO NOT TRUST" prompt rule.
3. **Mathematical tunnel vision (Case 5)** — Opus defaulted to reverse-engineering a function mathematically when the answer was a data investigation. Model switch to GPT-5.4 was the fix.
4. **Accumulated toxic context (Cases 4 & 5)** — wrong assumptions in case files poisoned every subsequent session. Clean slates were required.
5. **OTP captcha (Case 7)** — a mechanical challenge requiring parallel compute beyond agent capabilities. Required human intervention.

### Prompt evolution

| Version | Key changes | Effect |
|---------|-------------|--------|
| v3 | Base prompt | Cases 1-3 solved cleanly |
| v3-timed | No speculative submissions, time awareness | Too cautious — 0 submissions |
| v4-timed | Wrong answer reflection table, bias awareness | Better reasoning, still over-cautious |
| + persona | "Department head reviews your work" | Balanced caution with action — solved Case 4 |
| + no-brute-force | "DO NOT BRUTE-FORCE" | Prevented vocabulary sweeps on Case 5 |
| + CopsAI distrust | "DO NOT TRUST THE IN-GAME AI" | Prevented blind acceptance of hints |
| + model switch | GPT-5.4 for Cases 5-6 | Broke through Case 5 with different reasoning approach |
| + Occam's Razor | "Prefer N params over N+1" | Correct 2-arg interpretation on Case 7 |
| + Performance clue | "If solution doesn't fit time window, revisit assumptions" | General principle for timed puzzles |

### Comparison with prior challenges

| Metric | Challenge 1 | Challenge 2 | Challenge 3 |
|--------|-------------|-------------|-------------|
| Cases | 10 | 5 | 10 |
| Clean solves (1st iteration) | 8/10 | 4/5 | 8/10 |
| Human interventions | 1 (image OCR) | 1 (image OCR) | 1 (OTP captcha) |
| Blunder cases | 0 | 0 | 2 (Cases 4, 5) |
| Models used | 1 (Opus) | 1 (Opus) | 2 (Opus + GPT-5.4) |
| Bundles used | 1 (v3) | 1 (v3) | 2 (v3, v4-timed) |
| Prompt iterations | 0 | 0 | 8 |
| KQL queries | 285 | 144 | ~200 |

Challenge 3 was significantly harder than Challenges 1 and 2 — it forced prompt engineering evolution, model switching, and exposed fundamental agent limitations (parallel compute, CopsAI trust). The two blunder cases (4 and 5) consumed more effort than all of Challenge 2 combined.

### KQL Deep Dive

**~200 KQL queries** across successful sessions (25% of all tool calls).

#### Queries per case (successful sessions only)
| Case | KQL Queries | Total Tools | KQL % | Notes |
|------|-------------|-------------|-------|-------|
| 1-3 (combined session) | 40 | 92 | 43% | Opus — high KQL density, data-heavy cases |
| 4 — Dance with Shadows | 49 | 80 | 61% | Opus — highest KQL % (network/file transfer tracing) |
| 5 — Top GreyNet Priority | 35 | 313 | 11% | GPT-5.4 — low KQL % due to heavy browser + Python usage |
| 6 — Hack this Rack! | 12 | 93 | 13% | GPT-5.4 — mostly transcript analysis, few queries needed |
| 7 — One Shot. Use It Right. | 2 | 20 | 10% | Opus — site already solved, minimal KQL |
| 8 — Still in the Woods | 18 | 46 | 39% | Opus — power flow graph computation |
| 9 — Smoke Signals from YACC | 42 | 101 | 42% | Opus — graph-match traversal on 42M events |
| 10 — The Final Call | 2 | 64 | 3% | Opus — meta-puzzle with no database tables; PI digit search done in Python |

Cases 4 and 9 were the most KQL-intensive (61% and 42%). Case 10 barely used KQL — it was a meta-puzzle with no new database tables. The challenge involved conversing with CopsAI (browser), downloading 10M digits of PI via `external_data`, then searching for pandigital sequences and computing permutation distances — all done in Python because it's a string/math problem, not a data query problem.

#### Specialized KQL: New Concepts in Challenge 3

Challenge 3 introduced several advanced KQL features not seen in Challenges 1 or 2. Here's how the agent handled each:

**`graph-match` / Persistent Graph Model (Case 9 — 15 queries, 0 errors)**

The agent used `graph()` + `graph-match` extensively and confidently — building the YACC graph model snapshot, then running depth-20 traversals to trace Application → Workload → Process chains across 42M events. All 15 queries executed cleanly with zero syntax errors.

Notably, the agent had **failed** at `graph-match` in Challenge 1 Case 9 — it got a syntax error (`variable edge 'path' edges don't have property 'IsVulnerable'`) and abandoned it for iterative joins. By Challenge 3, it had learned the correct syntax. This is one of the clearest examples of cross-challenge skill improvement.

Example query from Case 9:
```kql
graph('YaccGraph')
| graph-match (app)-[*1..10]->(proc)
    where labels(app) has "Application"
    and labels(proc) has "Process"
    project AppName = app.AppName, ProcessKey = proc.Key
| summarize Apps = make_set(AppName), AppCount = dcount(AppName) by ProcessKey
| where AppCount > 1
```

**`series_cosine_similarity` (Cases 5 — 1 query by GPT-5.4, 7 by Opus)**

GPT-5.4 used cosine similarity **once** — and that single query was the breakthrough that solved Case 5 (finding the "test" chat by comparing word vectors against the challenge vectors of all 1016 intercepted conversations).

Opus used the same function **7 times** in a failed session — but applied it to the wrong problem (trying to reverse-engineer the chatbot's mathematical function rather than searching for an anomalous chat). The function was available and correctly invoked by both models; the difference was in *what question they asked with it*.

**`hash_many` + `bitset_count_ones` (Case 7 — 8 queries in failed session)**

The agent correctly extracted this predicate from the decrypted hacker logs and ran `range` queries to brute-force responses. It understood the mechanics perfectly but stumbled on two fronts:
- Used the wrong 3-arg interpretation (`hash_many(challenge, reverse(challenge), tostring(n))`) instead of the simpler 2-arg version
- Used `tostring(n)` which was 2.5x slower than passing integers directly

The Occam's Razor prompt addition (added after this failure) helped the next session choose the simpler interpretation.

**`union hint.concurrency=8` (human only)**

This query parallelism hint was the key to solving the OTP captcha within the 60s window. The agent never discovered it — it's not a commonly documented KQL feature. The human used it in `solve_otp2.py` to run 8 concurrent range searches in a single query, reducing 8B candidate search from ~4 minutes to ~33 seconds.

#### Comparison: KQL usage across challenges
| Metric | Challenge 1 | Challenge 2 | Challenge 3 |
|--------|-------------|-------------|-------------|
| Total KQL queries | 285 | 144 | ~200 |
| KQL as % of tools | 37% | 22% | 25% |
| Most KQL-heavy case | Case 8 (69) | Case 4 (43) | Case 4 (49) |
| Least KQL-heavy case | Case 3 (8) | Case 1 (5) | Case 10 (2) |

Challenge 3 used fewer KQL queries per tool call than Challenge 1, reflecting more browser interaction (NFZ site, GreyNet chatbot) and Python computation (PI digits, vector math).

### Recommendations for future challenges
1. **Parallel KQL execution** — add a tool that can fire multiple KQL queries concurrently for time-sensitive challenges
2. **CopsAI interaction protocol** — formalize "ask for directives, never seek confirmation" as a reusable skill
3. **Automatic clean-slate detection** — if 3+ consecutive sessions fail on the same case, automatically wipe accumulated context
4. **Model rotation** — if one model fails 3+ sessions, automatically try a different model
