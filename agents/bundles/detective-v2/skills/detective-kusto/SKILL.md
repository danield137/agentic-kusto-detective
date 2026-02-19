---
name: detective-kusto
description: "Expert knowledge for solving Kusto Detective Agency challenges at detective.kusto.io. Covers SPA navigation, challenge reading, answer submission, and KQL investigation patterns."
---

# Kusto Detective Agency — Agent Skill

## Critical Rules

1. **MUST use Playwright MCP** to navigate to the challenge page and read its full text.
2. **MUST use Playwright MCP** to submit answers on detective.kusto.io.

## Site Interaction

Use the Playwright MCP tools for ALL site interaction.

### Login procedure (MUST do this first, before anything else on the site)

1. Navigate to `https://detective.kusto.io`
2. Click the "Log in" link/button
3. Fill the cluster URI input field (`input[placeholder='Cluster URL']`) with the value of `DETECTIVE_CLUSTER_URI`
4. Click the "Log In" button to submit
5. Dismiss any post-login modals by pressing Escape a few times
6. You are now logged in — navigate to challenge pages from here

### Reading challenges

- **Do NOT navigate directly** to `https://detective.kusto.io/inbox/<case_name>` — the site is a Single Page App and direct URLs return 404
- Instead, after logging in, you are on the inbox page (`/inbox`)
- Click on the case name in the sidebar/list to open it (e.g. "Case 1 - Lieutenant Laughter")
- Read the full page content including training sections and hints
- The challenge text contains the problem description, data ingestion commands, and the question to answer

### Submitting answers

- Find the answer input field on the challenge page
- Enter your answer and click the submit button
- Read the page response to confirm if your answer was correct

### Screenshots and visual clues

- **Take screenshots early and often** to properly evaluate what you are looking at and look for visual clues
- Use the **image-analysis** skill (3-pass protocol) to analyze each screenshot

## Kusto Cluster Info

- **Cluster URI**: Read from `DETECTIVE_CLUSTER_URI` environment variable
- **Database**: The detective challenges use `MyDatabase` on free-tier clusters. If the database doesn't exist, check `.show databases` and use what's available.
- Use `kusto_explore` first (cached), then `kusto_query` for investigation

## KQL Tips

- KQL is NOT SQL — use pipe syntax: `Table | where ... | summarize ...`
- Start with schema exploration: `.show tables`, `TableName | take 5`
- Use `arg_min(Timestamp, col)` to find first occurrence
- Use `tolong(Properties.Field)` to extract dynamic properties
- Use `ipv4_is_in_range()` and `ipv4_lookup()` for IP analysis
- For large datasets, always start with `| take 100` or `| summarize count()`

