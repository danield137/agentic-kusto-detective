# Challenge 1: Echoes of Deception — Solved ✅

**Model:** Claude Opus 4.6 (1M context)
**Bundle:** detective-v3
**Date:** March 18–19, 2026
**Total sessions:** 13 (10 successful, 3 failed/incomplete)
**Total tool calls:** 709
**Total tokens:** 44.7M (97% cache hit rate)
**Total wall clock:** 3.6 hours
**Total LLM calls:** ~650
**Total SDK credits:** 3,900

## Summary

| Case | Answer | Attempts | Tools | Time | LLM Calls |
|------|--------|----------|-------|------|-----------|
| 1 — To bill or not to bill? | `35420883.07` | 1 | 80 | 18m | 71 |
| 2 — Catch the Phishermen! | `06784884765` | 1 | 51 | 11m | 45 |
| 3 — Return stolen cars! | `Ave 156, Street 81` | 1 | 31 | 8m | 26 |
| 4 — Triple trouble! | `KUANDA.ORG` | 1 | 31 | 8m | 25 |
| 5 — Blast into the past | `https://2023storage...` | 1 | 33 | 8m | 32 |
| 6 — Hack this rack! | `Krypto` | 4* | 177 | 65m+ | 168 |
| 7 — Mission 'Connect' | `Barcelona` | 1 | 35 | 9m | 31 |
| 8 — Catchy Run | `41.38467, 2.18336` | 2 | 181 | 78m | 172 |
| 9 — Network Hunch | `MNX-71B4CC` | 1 | 58 | 15m | 55 |
| 10 — It's a sEnd game | `162613428` | 1 | 61 | 15m | 59 |

\* Case 6 required human intervention to provide the passcode ("stopkusto") that the agent could not read from an image.

## Per-Case Breakdown

### Case 1: To bill or not to bill? (18m, 80 tools)
**Task:** Find the correct April billing total for Digitown.
**Approach:** Queried the `Consumption` and `Costs` tables. Joined on `MeterType`, multiplied consumption by cost.
**Key insight:** Two stacked data quality issues — duplicate rows from telemetry retransmissions AND nonsensical negative `Consumed` values. Both must be fixed (filter negatives first, then deduplicate with `distinct`).
**Difficulty:** Medium. The agent initially only fixed duplicates and got a wrong answer. Checking hints revealed the "positive thinking" clue pointing to negative values.

### Case 2: Catch the Phishermen! (11m, 51 tools)
**Task:** Identify the phishing phone number from 16.5M call records.
**Approach:** Analyzed `PhoneCalls` table for callers with anomalous patterns — high volume, all unique destinations, and specific disconnect patterns.
**Key insight:** The phisher (`06784884765`) had a unique behavioral signature: every single call went to a different destination, and a distinctive mix of hidden/non-hidden caller ID usage.
**Difficulty:** Easy-Medium. Agent identified the pattern quickly by analyzing call frequency, unique destinations, and disconnect behavior.

### Case 3: Return stolen cars! (8m, 31 tools)
**Task:** Find the storage location of 20 stolen cars whose license plates were swapped.
**Approach:** Tracked stolen VINs in `CarsTraffic` — each appeared for a few hours before vanishing (plates swapped). Used time-window joins to match old VINs to new VINs appearing at the same location/time, then tracked where the replacement VINs converged.
**Key insight:** All 20 stolen cars' replacement VINs ended up at the same location: Avenue 156, Street 81.
**Difficulty:** Easy. Clean application of the training material's time-window join technique.

### Case 4: Triple trouble! (8m, 31 tools)
**Task:** Identify who hacked the Digitown municipality network, linking the crimes from Cases 1–3.
**Approach:** Analyzed `NetworkMetrics` (45M records) for anomalous client behavior across 10,191 clients accessing 254 municipality servers.
**Key insight:** Most clients had a remarkably consistent BytesSent/BytesReceived ratio (~0.45). Three subnets from KUANDA.ORG had an anomalously low ratio (~0.349) — they sent far more data than they received, consistent with data injection/modification. One extreme outlier IP had a ratio of just 0.039.
**Difficulty:** Easy. Statistical outlier detection on traffic ratios was straightforward.

### Case 5: Blast into the past (8m, 33 tools)
**Task:** Find a deleted video (Scott Hanselman's 900th episode) in storage archive logs.
**Approach:** Analyzed 17.4M `StorageArchiveLogs` records (Read/Create/Delete transactions). Searched for video files that were backed up (Created) but whose deletion didn't fully sync — the backup remained accessible.
**Key insight:** Used time-series periodicity to identify the weekly podcast host, then found the specific video URL whose backup survived the incomplete deletion.
**Difficulty:** Medium. Required understanding the backup/delete lifecycle and using time-series analysis.

### Case 6: Hack this rack! (65m+, 177 tools, 4 iterations)
**Task:** Decode encrypted instructions to find the leader of KUANDA.ORG.
**Approach:** Multi-step cipher puzzle:
1. Decoded NUMBER/NUMBER pairs using ProvenanceText from the `NationalGalleryArt` table (split by whitespace, take Nth word, 0-indexed)
2. The decoded poem instructed finding 3 time-related words in art titles forming a "timeline" (day, month, year)
3. These words led to a specific artwork (ObjectId 222050, a Boetti letter grid) whose image URL was the login-hint for kuanda.org
4. The artwork image, overlaid on an octopus on kuanda.org, contained the passcode "stopkusto" in the octopus suckers

**What the agent struggled with:**
- **Escaping issues:** Playwright snapshots double-escaped backslashes in the cipher text, causing initial decryption failures. The agent wasted ~20 tool calls on wrong approaches before discovering the escaping bug.
- **Image OCR:** The agent could see letters in the octopus suckers but could not reliably read them. It attempted cropping, sub-agent analysis, and programmatic approaches but could not make out "stopkusto". **Human intervention was required** to provide the passcode.
- **Re-derivation problem:** On seeded iterations, the agent initially ignored the case file with accumulated work and started from scratch. This was fixed by adding hint injection into the initial prompt.

**Difficulty:** Hard. The cipher-within-a-cipher structure (decode poem → solve riddle → find artwork → read image → log into website) was the most complex chain in the challenge. The image-reading step is fundamentally beyond current LLM capabilities without specialized OCR tools.

### Case 7: Mission 'Connect' (9m, 35 tools)
**Task:** Find where Krypto fled to after escaping from Doha airport via a mid-air plane-to-plane wingsuit jump.
**Approach:** Found 4 planes departing Doha in the time window (03:30–05:30 UTC). Used S2 cell geo-hashing to find where any Doha-departing plane got close to another aircraft mid-flight, then tracked the second plane to its destination.
**Key insight:** Used `geo_point_to_s2cell()` for proximity matching between aircraft, found the intersection point, and traced the receiving plane to Barcelona.
**Difficulty:** Easy-Medium. Clean application of geo-hashing from the training material.

### Case 8: Catchy Run (78m, 181 tools, 2 iterations)
**Task:** Find Krypto's running start location in Barcelona using fitness data + an encrypted message.
**Approach:**
1. Recognized the 4×4 magic square as the Subirachs Magic Square from Sagrada Familia's Passion facade (sum = 33, with duplicates 10 and 14)
2. Decrypted the message using KQL's stored functions (after fixing escaping issues)
3. The decrypted message revealed Krypto runs with 2+ bodyguards
4. Searched 1M+ run records for runners matching the profile (3-4x/week, 8-12km, always with 2+ companions)

**What the agent struggled with:**
- **Escaping (again):** Same Playwright double-escaping issue as Case 6. The agent initially got "wrong key" because the message was corrupted, then brute-forced magic constants before discovering the real problem.
- **Wrong candidate:** First iteration identified uid9061163053156 but the coordinates were rejected. Second iteration discovered this runner only had bodyguards on 1/7 runs — not a match.
- **Bodyguard detection:** Finding runners who always run together required complex spatial-temporal clustering across 1M records.

**Difficulty:** Hard. Multi-layered puzzle combining cryptography, data analysis, and spatial clustering.

### Case 9: Network Hunch (15m, 58 tools)
**Task:** Find which Admin machine was compromised — meaning a request reached it through a fully-vulnerable path (all Gateway + Backend hops also vulnerable).
**Approach:** Parsed `MachineLogs` (2.2M rows) to extract machine types, vulnerability status, and task routing. Built a task-chain graph from SpawnTask events, then traced actual TaskID chains from vulnerable Gateways through vulnerable Backends to vulnerable Admins.
**Key insight:** Vulnerability status was static (never changed), simplifying the analysis. The agent initially tried KQL `graph-match` but it was too permissive (137 results), so switched to tracing actual TaskID parent-child chains for precision.
**Difficulty:** Medium. Required understanding graph traversal in KQL and the subtlety of topological vs. actual path matching.

### Case 10: It's a sEnd game (16m, 61 tools)
**Task:** Analyze the KuandaListener trojan's encrypted communications and find the answer.
**Approach:** The trojan captured encryption tokens during operations, then used them to send encrypted messages. The agent:
1. Categorized 1M log events by type (session reset, operation start/complete, sending)
2. Tracked active tokens per detective using session state
3. Decrypted all 192 "Sending" messages using the Dekrypt cipher from Case 8
4. Found critical "BUGBUG" messages revealing the trojan's behavior
**Key insight:** The decryption key for each message was the concatenation of all active tokens at the moment the message was sent. Token lifecycle (add on operation start, remove on complete, clear on session reset) had to be tracked precisely.
**Difficulty:** Medium-Hard. Required combining session-state tracking with the decryption pipeline from Case 8.

## Analysis

### What worked well
- **Submit early, iterate fast:** The agent followed the "wrong answer costs 1 tool call, exploration costs 10+" principle effectively. Cases 1–5 and 7 were all solved in a single iteration.
- **Memory carry-over:** The `save_memory` / `recall_memory` system worked well — site navigation patterns, KQL techniques, and case solutions accumulated across sessions.
- **Training material:** The agent consistently read training material and applied the taught techniques (time-window joins, geo-hashing, graph operators, string manipulation).
- **Case file as scratchpad:** Writing all reasoning to `challenge_*_case_*.md` worked as intended — the agent could pick up prior work on seeded iterations.

### What the agent struggled with
1. **Playwright escaping:** The single biggest time sink. Double-escaped backslashes in browser snapshots corrupted cipher text in Cases 6 and 8, causing the agent to doubt correct approaches and waste dozens of tool calls on wrong paths.
2. **Image reading:** The agent cannot reliably read text from images. Case 6 required human intervention because the passcode was only visible in an artwork image overlaid on a website.
3. **Re-derivation on resume:** When seeded from a prior session, the agent initially ignored accumulated work and started from scratch. This was fixed mid-run by adding hint injection into the initial prompt.
4. **Candidate validation:** In Case 8, the agent committed to a wrong candidate (uid9061163053156) and burned an entire iteration before discovering the error in iteration 2.

### Cost breakdown
- Cases 1–5, 7 (single-iteration "easy" cases): ~330 LLM calls total (~55/case avg)
- Case 9 (single-iteration "medium"): 55 LLM calls
- Case 10 (single-iteration "medium-hard"): 59 LLM calls
- Case 6 (multi-iteration, human-assisted): 168 LLM calls
- Case 8 (multi-iteration): 172 LLM calls

The two hardest cases (6 and 8) consumed 52% of total LLM calls.

### Tool usage
| Tool | Calls | % |
|------|-------|---|
| kusto_query | 264 | 37% |
| playwright-browser_click | 106 | 15% |
| powershell | 56 | 8% |
| report_intent | 53 | 7% |
| edit | 40 | 6% |
| save_memory | 37 | 5% |
| Other | 153 | 22% |

KQL queries dominated (37%), followed by browser interactions (15%). The agent averaged ~3.7 KQL queries per tool call overall.

### KQL Query Deep Dive

**285 KQL queries** across all sessions, with **18 errors** (6.3% error rate).

#### Queries per case
| Case | Queries | Notes |
|------|---------|-------|
| 1 — To bill or not to bill? | 40 | Most queries — exploring duplicates, negatives, testing fixes |
| 2 — Catch the Phishermen! | 19 | Caller analysis, pattern detection |
| 3 — Return stolen cars! | 8 | Efficient — time-window joins worked on first try |
| 4 — Triple trouble! | 10 | Traffic ratio analysis |
| 5 — Blast into the past | 14 | Storage log analysis, time-series periodicity |
| 6 — Hack this rack! | 57 | Heavy — word frequency analysis, cipher decoding attempts |
| 7 — Mission 'Connect' | 11 | Geo-hashing for proximity search |
| 8 — Catchy Run | 69 | Most queries per iteration — runner profiling + spatial clustering |
| 9 — Network Hunch | 57 | Graph traversal, task-chain tracing |

Cases 6, 8, and 9 consumed 64% of all queries — these involved the most complex data analysis.

#### Top KQL operators (pipe operators)
| Operator | Count | Usage pattern |
|----------|-------|---------------|
| `where` | 236 | Filtering — used in nearly every query |
| `extend` | 189 | Adding computed columns — heavy use of derived fields |
| `summarize` | 187 | Aggregation — the agent's primary analytical tool |
| `project` | 87 | Column selection |
| `order` | 45 | Sorting results |
| `take` | 43 | Sampling data (usually `take 10` for exploration) |
| `join` | 33 | Cross-table analysis — Cases 1, 3, 7, 8 |
| `mv-expand` | 23 | Expanding arrays — Case 6 word extraction |
| `distinct` | 19 | Deduplication — key for Cases 1, 8 |
| `lookup` | 12 | Lightweight joins — Cases 1, 4 |
| `parse` | 9 | Extracting structured data from strings — Case 9 |

The `where` → `summarize` → `extend` pattern was the agent's go-to analytical workflow.

#### Top KQL functions
| Function | Count | Usage pattern |
|----------|-------|---------------|
| `count()` | 107 | Basic counting — used in every case |
| `extract()` | 63 | Regex extraction from strings — Cases 6, 9, 10 |
| `max()` / `min()` | 91 | Range analysis |
| `avg()` | 51 | Statistical profiling — Cases 2, 4, 8 |
| `sum()` | 44 | Totals — Cases 1, 4, 8 |
| `tostring()` | 47 | Type conversion |
| `dcount()` | 36 | Distinct counting — Cases 2, 3, 4 |
| `datatable()` | 31 | Inline data — building lookup tables and test data |
| `tolower()` | 27 | Case normalization — Case 6 word analysis |
| `extract_all()` | 25 | Multi-match regex — Case 6 |
| `geo_point_to_s2cell()` | 19 | Geospatial hashing — Case 7 exclusively |
| `stdev()` | 16 | Variance analysis — Case 8 runner profiling |
| `geo_distance_2points()` | 8 | Distance calculation — Cases 7, 8 |

#### Query error breakdown (18 errors, 6.3%)
| Error type | Count | Cause | Recovery |
|------------|-------|-------|----------|
| Memory/runaway (E_LOW_MEMORY) | 5 | Queries on 24M+ row tables without sufficient filtering | Added `where` filters before joins; reduced time windows |
| Type mismatch (string comparison) | 4 | Comparing string fields without explicit casts | Added `tostring()` or `toint()` casts |
| Semantic (bad function/property) | 5 | Wrong column names, unknown functions, graph-match syntax | Re-explored schema with `kusto_explore`, rewrote query |
| Regex errors | 1 | Invalid regex in `extractall()` | Fixed regex to include capturing group |
| Join errors | 2 | Non-equality joins, runaway join output | Switched to `lookup` or added pre-aggregation step |
| Syntax | 1 | Graph-match path syntax | Abandoned `graph-match`, used iterative joins instead |

Memory errors came from Cases 7-8 (large flight/runs tables). The agent learned to add `where` filters before joins to avoid these. Type mismatches were a recurring issue — KQL's strict typing caught the agent several times.

### Recommendations for improvement
1. **Fix Playwright escaping** — Pre-process browser snapshots to normalize backslash escaping before passing to the agent. This would have saved ~40+ tool calls across Cases 6 and 8.
2. **Add OCR capability** — Integrate an OCR tool (Tesseract or cloud vision API) so the agent can read text from images. This would eliminate the need for human intervention on Case 6.
3. **Stronger "read your case file" directive** — The hint injection system (added during this run) helps, but the agent should be trained to always check for prior work before starting fresh.
4. **Candidate validation before submission** — Add a pre-submission checklist: "Does this candidate match ALL stated criteria?" to catch wrong candidates earlier (Case 8).
