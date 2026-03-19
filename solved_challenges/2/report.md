# Challenge 2: New Shadows Over Digitown — Solved ✅

**Model:** Claude Opus 4.6 (1M context)
**Bundle:** detective-v3
**Date:** March 19, 2026
**Total sessions:** 7 (5 successful, 2 failed/incomplete)
**Total tool calls:** 651
**Total tokens:** 25.9M (96% cache hit rate)
**Total wall clock:** 2.7 hours
**Total LLM calls:** ~538
**Total SDK credits:** 3,228

## Summary

| Case | Answer | Attempts | Tools | Time | LLM Calls |
|------|--------|----------|-------|------|-----------|
| 1 — The rarest book is missing! | `4242` | 1 | 25 | 7m | 20 |
| 2 — Election fraud? | `Kastor: 50.8%, Gaul: 38.6%, Willie: 6.6%, Poppy: 4.0%` | 1 | 76 | 20m | 73 |
| 3 — Bank robbery | `Avenue 42, Street 258` | 1 | 65 | 16m | 59 |
| 4 — Ready to play? | `wytaPUJM!PS:2,7,17,29,42,49,58,59,63` | 3* | 325 | 85m+ | 239 |
| 5 — Big heist | `2022-12-17, -3.3801, 58.9689` | 1 | 112 | 25m | 104 |

\* Case 4 required human intervention to provide the decrypt key ("ashes to ashes") visible on the El Puente building mural. Fair tool count to the image-reading wall: ~48.

## Per-Case Breakdown

### Case 1: The rarest book is missing! (7m, 25 tools)

**Task:** Find which shelf holds a rare book whose RFID sticker fell off.

**Approach:** The book's RFID won't appear in any shelf's list, but its physical weight is still on the shelf. Expanded each shelf's `rf_ids`, joined with the `Books` table to sum expected weights, then compared against reported `total_weight`.

**Key insight:** Shelf 4242 had a weight discrepancy of 1798g — close to the book's actual weight of 1764g (34g rounding across 46 books). All other shelves had differences of 0–50g.

**Difficulty:** Easy. Straightforward join + weight comparison.

---

### Case 2: Election fraud? (20m, 76 tools)

**Task:** Find the true election results after removing fraudulent votes.

**Approach:** Analyzed 5M+ votes across 10,326 IPs. Checked for duplicate voters (only 9 — negligible), temporal spikes (none), and per-IP voting patterns.

**Key insight:** The fraud was bots spamming rapid-fire Poppy votes — dozens per second from the same IP. Real voters cast at most 1 vote per (IP, second). Filtering to 1 vote per (IP, second) combination revealed the true winner was Kastor (50.8%), not Poppy.

**What the agent struggled with:** Took ~20 queries to identify the fraud mechanism. Initially looked at duplicate voter IDs, IP distributions, and temporal patterns — all red herrings. The breakthrough came from analyzing vote rate per IP per second.

**Difficulty:** Medium. The fraud mechanism was subtle — no obvious spikes or duplicate IDs.

---

### Case 3: Bank robbery (16m, 65 tools)

**Task:** Find where 3 bank robbers fled to after robbing a bank at Avenue 157 / Street 148.

**Approach:** Found cars present at the bank during the robbery window (08:17–08:31), then tracked their movements to find where they converged and parked permanently.

**Key insight:** Three cars (XC2952A7FB, RI8E6C4294, CXDE148D63) were at the bank right after the robbery, drove different directions, and all converged at Avenue 42, Street 258 — their hideout.

**What the agent struggled with:** Multiple days in the dataset had 3 cars at the bank during the time window. The agent had to figure out which day was the actual robbery by cross-referencing car behavior (permanent parking after the event).

**Difficulty:** Medium. Required temporal reasoning across 66M traffic records.

---

### Case 4: Ready to play? (85m+, 325 tools, 3 iterations)

**Task:** Decode a cipher text through a multi-step puzzle chain.

**Approach:** Five-step puzzle:
1. Found largest "special prime" under 100M = 99999517 (sum of two consecutive primes + 1)
2. Visited `https://aka.ms/99999517` → instructions about NYC tree census data
3. Used H3 geospatial cells to find a Turkish Hazelnut + 4 Schubert Chokecherries + smallest American Linden → Williamsburg, Brooklyn near El Puente
4. The El Puente building mural reads "ASHES TO ASHES" — the decrypt key (also a David Bowie song, matching the hint "catchy phrase is a key for a successful song too")
5. `Decrypt(cipher, "ashes to ashes")` → answer code

**What the agent struggled with:**
- **Wrong geospatial method:** Used cross-joins instead of H3 cells (as Hint 2 suggested), leading to a wrong location (Jamaica, Queens instead of Williamsburg). Wasted ~69 tools at the wrong Street View location.
- **Image reading:** Even at the correct location, the agent could not read "ASHES TO ASHES" from the El Puente mural in screenshots. **Human intervention was required** to provide the decrypt key.
- **Fair tool count:** ~48 tools to reach the point where only image-reading (not AI-solvable) remained.

**Difficulty:** Hard. The longest puzzle chain in the challenge (prime numbers → URL → tree census → geospatial → street view → song reference → decryption).

---

### Case 5: Big heist (25m, 112 tools)

**Task:** Find a heist gang of 4 in chat logs, determine the heist date and location.

**Approach:** Analyzed 3.8M chat log entries across 220K users. Identified the gang by finding a 4-user clique — users who only communicated with each other via a private channel. Extracted their IPs, visited sneakinto URLs for clues, then decoded historical references to pinpoint the heist.

**Key insight:** The gang (4 users in channel `cf053de3c7b`) had identical activity profiles — they only participated in that one channel and nowhere else. Their IPs led to a series of clues involving historical events, cryptographic hints, and geographic coordinates pointing to the heist location.

**What the agent struggled with:** Finding the 4-clique among 220K users required multiple query strategies. Initial approaches (users with exactly 3 DM contacts, channels with exactly 4 members) returned too many candidates. The breakthrough was filtering for users whose entire activity was confined to a single channel.

**Difficulty:** Hard. Combined graph analysis on large chat data with a multi-step clue chain (IPs → websites → historical references → coordinates).

## Analysis

### What worked well
- **First-try solves:** Cases 1, 2, 3, and 5 all solved in a single iteration — no retries needed.
- **Memory carry-over:** Navigation patterns and KQL techniques from Challenge 1 transferred well. The agent already knew how to use `mv-expand`, geo functions, and time-based filtering.
- **Efficient data ingestion:** The agent correctly identified when data needed to be ingested via `.create-merge table` commands and handled large CSVs (prime numbers, tree census) appropriately.

### What the agent struggled with
1. **Geospatial methods:** Case 4 used cross-joins instead of H3 cells despite the hint explicitly recommending them. This led to a wrong location and 69 wasted tools.
2. **Image reading (again):** Same limitation as Challenge 1 Case 6 — the agent cannot reliably read text from real-world images/murals.
3. **Large search spaces:** Cases 2 and 5 required multiple query strategies before finding the right signal among millions of records.
4. **Multi-step puzzle chains:** Case 4's five-step chain (primes → URL → trees → street view → decrypt) was the most complex, with each step depending on the previous one being correct.

### Cost breakdown
- Cases 1, 2, 3 (single-iteration): ~166 tools, ~44m total
- Case 5 (single-iteration, complex): 112 tools, 25m
- Case 4 (multi-iteration, human-assisted): 325 tools, 85m+

Case 4 alone consumed 50% of all tool calls.

### Tool usage
| Tool | Calls | % |
|------|-------|---|
| kusto_query | 144 | 22% |
| view | 108 | 17% |
| powershell | 67 | 10% |
| playwright-browser_click | 57 | 9% |
| report_intent | 46 | 7% |
| web_fetch | 42 | 6% |
| Other | 187 | 29% |

Notably higher `web_fetch` usage (42 calls, 6%) compared to Challenge 1 — Case 4's puzzle chain required visiting external URLs and downloading files.

### KQL Query Deep Dive

**144 KQL queries** across all sessions, with **13 errors** (9.0% error rate — higher than Challenge 1's 6.3%).

#### Queries per case
| Case | Queries | Notes |
|------|---------|-------|
| 1 — The rarest book is missing! | 5 | Very efficient — weight comparison was straightforward |
| 2 — Election fraud? | 40 | Heavy — exploring multiple fraud hypotheses |
| 3 — Bank robbery | 31 | Tracking car movements across 66M records |
| 4 — Ready to play? | 43 | Tree census + geospatial + decrypt attempts |
| 5 — Big heist | 25 | Chat log graph analysis |

#### Top KQL operators
| Operator | Count | Usage pattern |
|----------|-------|---------------|
| `where` | 102 | Filtering — used in nearly every query |
| `summarize` | 98 | Aggregation — primary analytical tool |
| `extend` | 59 | Computed columns |
| `order` | 35 | Sorting results |
| `project` | 20 | Column selection |
| `take` | 15 | Sampling data |
| `join` | 7 | Cross-table analysis |
| `mv-expand` | 7 | Expanding arrays (shelf RFID lists, chat channels) |

#### Query error breakdown (13 errors, 9.0%)
| Error type | Count | Cause | Recovery |
|------------|-------|-------|----------|
| Memory/runaway | 3 | Large joins on 66M+ row tables | Added time/location filters before joins |
| Semantic (unknown table/function) | 4 | Wrong table names, missing functions | Re-explored schema, ingested data |
| Type mismatch | 3 | String comparison without casts | Added explicit `tostring()` casts |
| Syntax/logic | 3 | Dynamic type grouping, scalar context | Rewrote with `tostring()`, used `print` |

### Comparison with Challenge 1

| Metric | Challenge 1 | Challenge 2 |
|--------|-------------|-------------|
| Cases | 10 | 5 |
| Total tools | 709 | 651 |
| Total time | 3.6h | 2.7h |
| KQL queries | 285 | 144 |
| Query error rate | 6.3% | 9.0% |
| Human interventions | 1 (Case 6) | 1 (Case 4) |
| Single-iteration solves | 8/10 | 4/5 |
| Hardest case tools | 181 (Case 8) | 325 (Case 4) |

Challenge 2 had fewer cases but similar total effort. Both challenges had exactly one case requiring human intervention for image reading. The query error rate was slightly higher, reflecting more complex data structures (dynamic arrays, H3 cells).
