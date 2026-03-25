# Challenge 3: Call of the Cyber Duty — In Progress

**Model:** Claude Opus 4.6 (1M context)
**Bundle:** detective-v4-timed (Cases 4+), detective-v3 (Cases 1-3)
**Date:** March 19–24, 2026

## Summary

| Case | Answer | Attempts | Tools | Time | Notes |
|------|--------|----------|-------|------|-------|
| 1 — Nuclear Fusion Breach! | `13 Ave, 37 St` | 1 | 71 | 15m | |
| 2 — Coffee Trails | `Rima Zen` | 1 | 31 | 8m | |
| 3 — Silent Tap | `GREYNET.TO` | 1 | 50 | 10m | |
| 4 — Dance with Shadows | `d2025-05-07-11-10/80.237.254.8/ca2m3h28hlo.csv.gz` | 1* | 80 (+ 1,116 failed across 12 sessions, ~14h) | 24m | Major blunder — see below |
| 5 — TBD | | | | | |

\* Case 4 solved on first submission of the final session, but only after 12 failed sessions that never found the right answer.

## Per-Case Breakdown

### Case 1: Nuclear Fusion Breach! (15m, 71 tools)

**Task:** Find the Digitown address where hackers launched an attack on nuclearfusionzero.com.

**Approach:** The hacker poem mentioned "pizza heroes" and "Wednesday night — our weekly fame." Searched the `DeliveryOrders` table for addresses receiving pizza every Wednesday evening.

**Key insight:** 13 Ave, 37 St was a massive outlier — pizza delivered on ALL 13 Wednesdays in the data range, with group orders of 20-56 items each. The next highest address only had 6 Wednesdays.

**Difficulty:** Medium. Required decoding the hacker poem for clues, then correlating with delivery data.

---

### Case 2: Coffee Trails (8m, 31 tools)

**Task:** Find who the hackers were meeting with, using smart coffee machine Bluetooth logs.

**Approach:** Extracted 58 unique Bluetooth device hashes from the coffee machine at the known hacker location (13 Ave, 37 St). Cross-referenced against all 73,925 coffee machines in Digitown.

**Key insight:** Machine `GCM3182DC2276E26850` at 127 Ave, 42 St had 50 out of 58 matching hashes — the next best had only 2. Registration info: "Rima Zen".

**Difficulty:** Easy. Clean signal — the 50/58 match was overwhelming.

---

### Case 3: Silent Tap (10m, 50 tools)

**Task:** Find where stolen data from RimaZen's network was being exfiltrated to.

**Approach:** Analyzed 9M network log records. RimaZen's internal network (103.24.169-171.x) communicated with thousands of external IPs. Looked for the external destination receiving the most one-directional outbound data.

**Key insight:** GREYNET.TO owned 3 IP ranges with ~160 IPs, receiving data from ~160 different RimaZen internal IPs in highly regular patterns (exactly 30, 60, or 90 connections per pair). GREYNET.TO never sent any data back — purely one-way exfiltration.

**Difficulty:** Medium. Required distinguishing the exfiltration pattern from normal bidirectional traffic.

---

### Case 4: Dance with Shadows (24m, 80 tools — but see blunder below)

**Task:** Find the backup URL where the complete GreyNet dataset last existed before being split into 5 shards during a PMC conference call.

**Approach (final, successful session):** Started fresh with the v4-timed bundle. Identified PMC cities (256+ hackers), mapped IPs to cities, found the conference call, traced file transfers to find the complete dataset and its source IP.

**Answer:** `https://2025storagebackup.blob.core.windows.net/d2025-05-07-11-10/80.237.254.8/ca2m3h28hlo.csv.gz`

**Difficulty:** Very Hard. The hardest case across all three challenges.

#### The Case 4 Blunder

**What went wrong:** The agent spent 12 failed sessions (~1,116 tool calls, ~14 hours) anchored on the wrong event. In iteration 1, it found IP `49.73.36.163` sending 5 copies of a 64MB file to 5 PMC-city IPs on May 3. This looked perfect — but it was a red herring. The actual answer involved a completely different date (May 7), IP (80.237.254.8), and file (ca2m3h28hlo.csv.gz).

**Why it kept failing:**
1. **Anchoring bias** — The first plausible pattern (5 copies on May 3) became the anchor. Every subsequent iteration permuted this same IP/file/timestamp instead of questioning the fundamental assumption.
2. **Confirmation bias with CopsAI** — The agent asked CopsAI leading questions ("Is this the right IP?") and interpreted vague affirmations as hard confirmation.
3. **Accumulated case file was toxic** — Each iteration seeded from the previous one, carrying forward wrong hypotheses. The case file grew to 27,000 characters of wrong answers, stale analysis, and conflicting CopsAI guidance that steered every new session back to the same dead end.
4. **Rate limiting compounded the problem** — Each wrong submission triggered a 30-50 minute lockout, burning most of the 45-minute session timeout.

**What fixed it:** Three changes, applied together:
1. **Clean seed** — Seeded from the last session with only Cases 1-3 solved (no Case 4 history). This eliminated the toxic accumulated state.
2. **v4-timed bundle** — Added "Careful Observation Over Quick Conclusion" (avoid red herrings, survivorship bias, confirmation bias, anchoring) and "After a wrong answer" reflection table.
3. **Persona framing** — "Your department head reviews every case file" created stakes around reasoning quality, not just answer correctness.

**Result:** The fresh session solved it in 80 tools, 24 minutes, 1 submission — first try.

**Lesson:** When an agent is deeply anchored on a wrong hypothesis across multiple iterations, more iterations make it worse, not better. The accumulated case file becomes an anchor that prevents fresh thinking. Sometimes the best intervention is to wipe the slate and start over with better reasoning prompts.

---

### Case 5: TBD

*Placeholder — to be filled after solving.*

---

## Analysis

### What worked well
- **Cases 1-3 solved in single iterations** — clean, efficient investigations with clear signals
- **Coffee machine Bluetooth tracking (Case 2)** — elegant cross-referencing of device hashes
- **v4-timed bundle** — prevented reckless submissions on Case 4 (0 submissions on cautious sessions vs 3+ on v3 sessions)
- **Clean seed strategy** — wiping toxic state was the breakthrough for Case 4

### What the agent struggled with
1. **Anchoring on red herrings (Case 4)** — the 5-copy pattern on May 3 was structural noise (162 files had this pattern), not the specific scatter event
2. **CopsAI confirmation bias** — treating directional hints as hard answers
3. **Over-caution with v4-timed** — one session used 92 tools with 0 submissions (too cautious)
4. **Rate limiting** — each wrong answer on Case 4 burned 30-50 minutes of a 45-minute session

### Prompt evolution during this challenge
| Version | Key changes | Effect |
|---------|-------------|--------|
| v3 | Base prompt | Cases 1-3 solved cleanly |
| v3-timed | No speculative submissions, time awareness | Too cautious — 0 submissions |
| v4-timed | Wrong answer reflection table, "Careful Observation" section | Better reasoning but still 0 submissions |
| v4-timed + persona | "Department head reviews your work" | Balanced caution with action — solved Case 4 |
| v4-timed + convergence | "Have a candidate by ~80 tool calls" | Added after Case 4 solve |
