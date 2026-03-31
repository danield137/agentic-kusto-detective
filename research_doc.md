# KQL Research Analysis — Agent Usage Patterns & Improvement Opportunities

**Source:** 1,205 KQL queries across 50 sessions, 3 challenges (25 cases)
**Error rate:** 119 errors (9.9%), 67 unique error messages
**Models:** Claude Opus 4.6 1M, GPT-5.4
**Bundles:** detective-v3, detective-v4-timed

## Table of Contents

1. [Error Taxonomy](#1-error-taxonomy) — 119 errors classified by type
2. [Context Pollution](#2-context-pollution) — 25 oversized results
3. [Slow Queries](#3-slow-queries) — 35 queries over 10s
4. [Query Retries](#4-query-retries) — wasted effort from anchoring bias
5. [Python Fallback Analysis](#5-python-fallback-analysis) — 190 Python calls, 18% could have been KQL
6. [Kusto-Specific vs Generic](#6-kusto-specific-vs-generic) — what's actionable by the KQL team
7. [Auto-Correct Proposal](#7-auto-correct-proposal) — 56% of errors are deterministically fixable
8. [Server-Side Concepts](#8-server-side-concepts) — ideas for the remaining memory/runaway errors

---

## 1. Error Taxonomy

119 errors across 67 unique patterns. Classified by type:

### 1.1 Memory & Runaway Queries (21 errors, 18%)

The most impactful category. Agent hits cluster memory limits on unfiltered scans or join explosions.

```kql
-- C1 Case 1: Full summarize on 24M row table, no pre-filter
Consumption
| summarize dcount(Consumed), count() by Timestamp, HouseholdId, MeterType
| where dcount_Consumed > 1
-- Error: E_LOW_MEMORY_CONDITION: bad allocation
```

```kql
-- C3 Case 4: Cross-join explosion — 25K IPs × 195 polygons
ip_locs | join kind=inner (Cities4 | where EstimatedHackersCount >= 256) on ...
-- Error: E_RUNAWAY_QUERY: Join output block exceeded memory budget
```

### 1.2 Missing Functions / Plugins (5 errors)

Agent expected functions that don't exist on this cluster:

| Expected | Context | What the agent wanted |
|----------|---------|----------------------|
| `geo_point_in_polygon_lookup` | C3 Case 4 | Bulk point-in-polygon lookup (like `ipv4_lookup` for geo) |
| `minuteofhour` | C2 Case 3 | Minute component — actual: `datetime_part("minute", ts)` |
| `python` plugin | C3 Case 5 | Inline Python for vector math — disabled on free cluster |
| `geo_point_in_polygon` (as plugin) | C3 Case 4 | Exists as function but not as evaluate plugin |

### 1.3 `extract_all` Capturing Group Requirement (2 errors)

```kql
-- Agent wrote (Python-style):
extract_all(@'[a-zA-Z]{3,}', tolower(Title))
-- Error: extractall(): argument 2 must be a valid regex with [1..16] matching groups

-- KQL requires:
extract_all(@'([a-zA-Z]{3,})', tolower(Title))
```

### 1.4 Join Limitations (12 errors)

**Equality-only joins (5 errors):**
```kql
-- Agent wanted geo-distance threshold join
join on geo_distance_2points(a.lat, a.lon, b.lat, b.lon) < 1000
-- Error: join: Only equality is allowed in this context
```

**Dynamic-type join keys (4 errors):**
```kql
-- C3 Case 4: Join on dynamic column
join kind=inner pmc_cities on $left.Lon == $right.Area
-- Error: join key 'Area' is of a 'dynamic' type. Please use an explicit cast
```

**Join key mismatch (3 errors):**
```kql
-- Error: join: for each left attribute, right attribute should be selected.
-- Error: join: both sides of equality should be column entities only.
```

### 1.5 Dynamic Type Friction (7 errors)

```kql
-- C2 Case 5: Grouping by dynamic column
| summarize ... by Partners
-- Error: Summarize group key 'Partners' is of a 'dynamic' type

-- C2 Case 3: Ordering by dynamic column
| order by SomeColumn desc
-- Error: order operator: key can't be of dynamic type
```

Fix is always `tostring()`. Agent hit this 7 times across 5 cases.

### 1.6 String Comparison Strictness (4 errors)

```kql
-- C1 Case 8: Comparing S2 cell values
Runs
| extend startCell = geo_point_to_s2cell(StartLon, StartLat, 16)
| join kind=inner (...) on startCell
-- Error: Cannot compare values of types string and string. Try adding explicit casts
```

### 1.7 Syntax Errors (4 errors)

```kql
-- C3 Case 9: Management command in query pipe
.show tables | project TableName
-- Error: Unexpected control command

-- C3 Case 4: Reserved word as variable
let shard_info = ... shards ...
-- Error: The name 'shards' needs to be bracketed as ['shards']
```

### 1.8 Serialization Requirements (2 errors)

```kql
-- C3 Case 4: Window function without serialize
ChatServerLogs
| summarize Online = sum(Direction) by bin(Timestamp, 5m)
| extend CumulativeOnline = row_cumsum(Online)
-- Error: Function 'row_cumsum' cannot be invoked. The row set must be serialized.
```

### 1.9 `graph-match` Syntax Learning (2 errors, C1 only)

```kql
-- C1 Case 9: Incorrect property access on graph edges
graph-match (gw)-[path*1..3]->(admin)
    where path.IsVulnerable == true
-- Error: graph-match operator: variable edge 'path' edges don't have property 'IsVulnerable'
```

Agent failed twice in C1, then mastered `graph-match` by C3 (15 queries, 0 errors).

### 1.10 Unresolved Names (18 errors)

Agent used wrong table/column names. See [Section 7](#7-auto-correct-proposal) for fuzzy-match analysis — 89% are matchable against cached schema.

### 1.11 Network / Transient (7 errors)

```
Error: Failed to process network request for the endpoint: ...
```

6 of 7 had a corrupted cluster URI (Georgian characters injected — encoding bug in Playwright pipeline). Retryable.

---

## 2. Context Pollution

25 queries returned results too large for the agent's context window (up to 1.3 MB).

| Root Cause | Count | Example |
|-----------|-------|---------|
| No `| take` limit | 19 | Full table dumps |
| Huge rows (30KB vectors) | 4 | `GreyNetLogs | take 20` = 600KB |
| `make_list`/`make_set` explosions | 2 | Single 500KB cells |

Impact: agent loses inline data, must read temp files in separate tool calls, fragmenting reasoning.

---

## 3. Slow Queries

35 queries took >10s. Distribution:

| Duration | Count | Primary Pattern |
|----------|-------|-----------------|
| 10-15s | 18 | Full-table scans with complex filters |
| 15-20s | 10 | Join operations on large tables |
| 20-30s | 6 | Vector similarity (pairwise cosine on 1536-dim arrays) |
| 30s+ | 1 | 9M row network log analysis |

The 6 vector queries (20s+ each) all did approximate nearest-neighbor via round-and-join — a workaround for the lack of a native k-NN operator.

---

## 4. Query Retries

~14 near-identical queries with small parameter variations (different timestamps, IPs). Root cause is agent anchoring bias, not a KQL issue. Already addressed in the v4-timed prompt's "Pivot after 3 failures" rule.

---

## 5. Python Fallback Analysis

190 Python tool calls across all sessions. Breakdown by what Python was used for:

| Category | Count | Could KQL do this? | Examples |
|----------|-------|--------------------|----|
| File I/O | 107 | No | Writing case files, reading temp results, saving artifacts |
| Iteration/loops | 74 | Partially — `mv-expand`, `mv-apply` | Processing arrays, sliding windows, combinatorics |
| Image processing | 56 | No | PIL cropping, letter recognition, screenshot analysis |
| Crypto (cipher/decode) | 44 | No* | Base64 decode with custom alphabets, XOR ciphers, Vigenère |
| Web fetch | 40 | Partially — `external_data` for CSVs | Downloading JS bundles, images, PDFs, prime number files |
| Data analysis | 15 | **Yes** | Counting, sorting, frequency analysis on exported data |
| Regex parsing | 13 | **Yes** | `extract`, `extract_all`, `parse` all exist in KQL |
| Vector math | 11 | **Partially** | Element-wise operations on 1536-dim arrays |
| Crypto (hash) | 9 | No | MD5/SHA256 for website authentication, not data analysis |
| Data processing | 6 | **Yes** | CSV parsing, filtering, joining — all core KQL |
| JSON parsing | 3 | **Yes** | `parse_json`, dynamic property access |

\* KQL has puzzle-specific stored `Decrypt`/`Dekrypt` functions, but the agent sometimes couldn't invoke them correctly (escaping issues) and fell back to Python.

### Where KQL could have replaced Python (34 calls, 18%)

**Data analysis on exported data (15 calls):**

The agent exported KQL results to temp files, then wrote Python to analyze them — counting, sorting, frequency analysis. This is exactly what `summarize`, `count`, `dcount`, `top` do natively.

Example (C1 Case 9, Opus): Agent exported KuandaLogs events to a text file, then wrote Python to parse and count event types:
```python
# What the agent did:
with open('kuanda_events.txt', 'r') as f:
    lines = f.readlines()
counter = Counter(line.split('|')[2].strip() for line in lines)
```
```kql
// What KQL could have done directly:
KuandaLogs | summarize count() by EventType | order by count_ desc
```

**Regex extraction (13 calls):**

Agent used Python `re.search`/`re.findall` on data already in Kusto tables. KQL's `extract`, `extract_all`, and `parse` operators handle the same patterns.

Example (C2 Case 5, Opus): Agent extracted user/channel names from chat log messages using Python regex:
```python
# What the agent did:
sender = re.search(r"User '([^']+)' sent", message).group(1)
```
```kql
// What KQL could have done:
ChatLogs | extend Sender = extract("User '([^']+)' sent", 1, Message)
```

**CSV/data processing (6 calls):**

Agent downloaded CSVs and processed them in Python instead of using `external_data` or ingestion.

Example (C2 Case 4, Opus): Downloaded and parsed a prime numbers CSV in Python:
```python
# What the agent did:
import gzip, csv
with gzip.open('prime-numbers.csv.gz', 'rt') as f:
    primes = [int(line.strip()) for line in f]
```
```kql
// What KQL could have done:
let primes = external_data(prime:long)
  [h@'https://kustodetectiveagency.blob.core.windows.net/prime-numbers/prime-numbers.csv.gz']
  with (ignoreFirstRecord=true);
primes | where prime < 100000000 | summarize max(prime)
```

### Where Python was the right choice (156 calls, 82%)

- **Image processing (56):** PIL for cropping artwork, letter recognition, screenshot analysis. KQL has no image capabilities.
- **Cryptography (53):** Custom ciphers, base64 with modified alphabets, hash computation for website auth. KQL's `hash()` is for data operations, not cryptographic puzzles.
- **Web fetching (40):** Downloading JS bundles, PDFs, images. `external_data` only handles tabular CSVs.
- **File I/O (107):** Writing case files, reading temp results. Inherent to the agent's workflow.

### Model comparison

| Metric | Opus (129 calls) | GPT-5.4 (61 calls) |
|--------|-----------------|---------------------|
| **Data analysis in Python** | 6 calls (5%) | 9 calls (15%) |
| **Regex in Python** | 8 calls (6%) | 5 calls (8%) |
| **Vector math in Python** | 6 calls (5%) | 5 calls (8%) |
| **Overall KQL-replaceable** | ~20 calls (15%) | ~14 calls (23%) |

GPT-5.4 has a **higher rate** of using Python where KQL would work (23% vs 15%). This aligns with the broader observation: GPT-5.4 is more comfortable with Python and reaches for it sooner, while Opus prefers KQL (35% of its tool calls are KQL vs GPT's 11%).

### The vector math case (C3 Case 5, GPT-5.4)

The most notable KQL-avoidance pattern. GPT-5.4 queried Kusto to extract vectors, then processed them in Python:

```python
# GPT-5.4 exported vectors and computed cosine similarity in Python
from azure.kusto.data import KustoClient
result = client.execute(db, "GreyNetSecretData | where Word == 'test' | project Vec")
vec = parse_vector(result)
# ... manual cosine similarity loop
```

KQL has `series_cosine_similarity` which does this natively. The same session's Opus counterpart used it directly:

```kql
// Opus used KQL for the same operation
let target = toscalar(GreyNetSecretData | where Word == "test" | project Vec);
GreyNetLogs | where Message in (0, 2, 4)
| extend sim = series_cosine_similarity(parse_json(Text), target)
| top 5 by sim desc
```

GPT-5.4 chose Python not because KQL couldn't do it, but because it's more fluent in Python data processing. This suggests that **KQL tool discoverability** could be improved — the agent needs clearer signaling that `series_cosine_similarity` exists and handles this use case.

---

## 6. Kusto-Specific vs Generic

### Kusto-Specific (actionable by KQL team)

| Finding | Why Kusto-Specific | Impact |
|---------|-------------------|--------|
| Missing `geo_polygon_lookup` | Asymmetry with `ipv4_lookup` | ~20 tool calls wasted |
| No set-based `vector_search` | `series_cosine_similarity` is scalar only | 7 × 20s queries |
| `extract_all` needs capturing groups | Differs from all other regex engines | 2 errors |
| Dynamic type strictness in `summarize by`/`order by`/`join on` | SQL allows grouping by any type | 7 errors |
| `serialize` for `row_number()`/`row_cumsum()` | SQL window functions don't need this | 2 errors |
| Equality-only joins | Most SQL engines support inequality joins | 5 errors |
| String comparison cast requirement | Unique to KQL | 4 errors |
| `graph-match` learning curve | Unique syntax | 2 errors (self-corrected by C3) |
| Management/query plane split | SQL has no such split | 2 errors |

### KQL Error Message Quality

| Error | Agent Self-Correction Rate | Quality |
|-------|---------------------------|---------|
| Dynamic type cast hint | 100% | ✅ Tells you exactly what to do |
| `extractall` matching groups | 100% | ✅ Clear |
| `serialize` required | 100% | ✅ Clear |
| `Only equality allowed` | 60% | ⚠️ Doesn't suggest S2/H3 workaround |
| `string and string` comparison | 50% | ❌ Confusing — same type shouldn't need cast |
| `E_LOW_MEMORY_CONDITION` | 30% | ❌ No indication of which operator caused it |
| `graph-match` property errors | 0% first encounter | ❌ No syntax example in error |

### NOT Kusto-Specific (generic to any LLM + database)

- Large results overflowing context → tool-level result handling
- Memory errors from unfiltered scans → any underpowered DB instance
- Query retries from anchoring → agent reasoning problem
- Python fallbacks → model preference
- Agent not checking schema before querying → agent discipline

---

## 7. Auto-Correct Proposal

**56% of all errors (65 of 117) are deterministically handleable** without agent judgment, across 7 stages:

### Summary

| Stage | Type | Errors Handled | Mechanism |
|-------|------|---------------|-----------|
| 1. Pre-flight | Fix before execution | 14 | Parse query: fix `extract_all` groups, inject `serialize`, fix `external_data` syntax, fix `make_list` context |
| 2. Reroute | Wrong endpoint | 4 | Detect `.show` prefix → command endpoint; wrong database → correct DB |
| 3. Post-flight | Parse error, fix, retry once | 24 | Dynamic cast (`tostring()`), string comparison cast, bracket reserved words, wrap in `print`, function aliases, join key suggestions |
| 4. Fuzzy suggest | Enrich error message | 16 | "Did you mean?" against cached schema (89% match rate) |
| 5. Retry | Transient failures | 7 | Network errors with backoff; URI encoding validation |
| **Total** | | **65 (56%)** | |

### Key Design Decisions

- **Never refuse** — the query already ran, refusing wastes compute. Always return something useful.
- **Corrections are visible** — agent sees `[Auto-corrected: wrapped 'Partners' in tostring()]` so it learns the pattern.
- **One retry max** — post-flight fixes retry once. If the retry also fails, return the original error.
- **Fuzzy suggest doesn't auto-fix** — it enriches the error with "did you mean?" but lets the agent choose.

### Fuzzy Schema Matching (Stage 4 detail)

89% of "Failed to resolve" errors match against the cached schema from `kusto_explore`:

```
"Traffic" was not found. Did you mean:
  -> CarsTraffic (Timestamp:datetime, VIN:string, Ave:int, Street:int)

"NewVIN" was not found. Did you mean column:
  -> VIN (in tables: CarsTraffic, StolenCars)

"YaccApplications" was not found. Did you mean:
  -> YaccApplications (AppId:string, AppName:string, HostingIp:string)  [not yet ingested]
```

Root causes caught: not-yet-ingested tables (5), invented column names (6), wrong table from different challenge (3), let-variable scope errors (2).

---

## 8. Server-Side Concepts

The 21 memory/runaway errors are the largest remaining unfixable category. The auto-correct tool can't restructure queries (it doesn't know which filters to add), but the **error experience** can be improved server-side:

### Concept A: Memory Usage Breakdown in Error Messages

Current: `E_LOW_MEMORY_CONDITION: bad allocation`

Proposed: Include which operator caused the OOM and intermediate result sizes:
```
Memory limit exceeded at step 4 (join).
  Step 1: ChatServerLogs | where ... → 500K rows (180MB)
  Step 2: | distinct ClientIP → 25K rows (2MB)
  Step 3: | evaluate ipv4_lookup → 25K rows (95MB)
  Step 4: | join Cities4 → FAILED (estimated 5M output rows)
Suggestion: Add filters before the join to reduce input, or verify cardinality first.
```

### Concept B: Query Plan Preview (dry-run)

An `explain` or `hint.dryrun` mode that returns estimated cardinalities per step without executing — letting the agent check feasibility before committing. Similar to SQL's `EXPLAIN ANALYZE`.

### Concept C: Partial Results on Memory Failure

Instead of hard-failing, return results from completed steps with a warning about where it stopped. The agent gets actionable partial data instead of nothing.

### Feasibility Assessment

| Concept | Effort | Value | Notes |
|---------|--------|-------|-------|
| A: Memory breakdown | Medium | High | Some operator-level tracking exists already |
| B: Query plan preview | High | Medium | Requires cardinality estimation engine |
| C: Partial results | High | Highest | Requires streaming execution changes |
