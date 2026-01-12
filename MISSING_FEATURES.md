# Remaining V1 Features for V2 Architecture

These prompts cover features from V1 that were not included in the primary `DETAILED_PROMPTS.md`. Use these after completing the core setup.

## Step 6: Exclusion & Data Cleaning
**Goal:** Port the logic for ignoring specific transactions (e.g., transfers, payments) to prevent double counting or noise.

**V1 Context:** Handled via csv files `exclude.csv` and regex logic in pandas.
**V2 Improvement:** Store these rules in a database table so they are persistent and queryable.

**Prompt to Copy:**
```text
I need to implement the "Exclusion" feature to hide specific transactions from analytics.

1.  **Database:** Update `database/models.py`:
    *   Add `ExclusionRule` table.
    *   Columns: `id`, `rule_type` (e.g., 'exact_match', 'regex', 'category'), `value` (the string or pattern), `is_active` (boolean).
    *   Add `is_excluded` boolean column to the `Transaction` table (default False).

2.  **Seeding:** Update `services/seed_data.py` to import my existing `exclude.csv` and `exclude.txt`.
    *   If the existing file has raw strings, treat them as `rule_type='exact_match'` (or `regex` if they look like patterns).

3.  **Logic:** Update `services/importer.py` (or create `services/cleaner.py`):
    *   Function `apply_exclusions()`: Query all active rules.
    *   If a transaction matches a rule, set its `is_excluded` flag to `True`.
    *   This logic should run automatically during import.

4.  **UI:** Create `ui/pages/excluded.py` (or a tab in Settings):
    *   Grid 1: "Exclusion Rules" - Add/Edit/Delete patterns.
    *   Grid 2: "Excluded Transactions" - Show all rows where `is_excluded=True`. Allow manual toggle back to included.
```

---

## Step 7: "Deduplication" Tab (Advanced)
**Goal:** While the backend handles hashing, the V1 app had a specific tab to show "potential duplicates" for manual review.

**V1 Context:** User could select rows and "Remove Selected Duplicates".
**V2 Improvement:** Since strict hashing handles 99% of cases, this tool effectively becomes a "Conflict Resolver" or manual cleanup tool.

**Prompt to Copy:**
```text
I need to build a manual Deduplication / Cleanup tool in `ui/pages/cleanup.py`.

1.  **Logic:** We need a query to find "Similar Transactions" that might not have identical fingerprints (e.g., date off by 1 day).
    *   SQL: Find records with same `amount` and `clean_description` within +/- 2 days of each other.
2.  **UI:**
    *   Show these groups of potential duplicates.
    *   Allow the user to "Merge" (keep one, delete others) or "Ignore" (mark as distinct).
```

---

## Step 8: "Merchant Deep Dive" & Drill-downs
**Goal:** The V1 app had a specific tab for analyzing a specific merchant's history.

**V1 Context:** "Merchant Intelligence" tab with top N expenses and drill-down charts.
**V2 Improvement:** This should be a dynamic route or modal.

**Prompt to Copy:**
```text
I need to recreate the "Merchant Intelligence" feature.

1.  **Analytics:** Create a service function `get_top_merchants(start_date, end_date, limit=10)`:
    *   Returns aggregation by `standardized_merchant` (or `clean_description`).
    *   Sort by Net Volume.

2.  **UI:** In `ui/pages/dashboard.py` (or a new `ui/pages/merchants.py`):
    *   Display a list/chart of top merchants.
    *   **Drill-down:** When a merchant name is clicked, open a Dialog.
    *   **Dialog Content:** Show a mini-graph of spending over time for *just that merchant* and a list of their recent transactions.
```

---

## Step 9: Global Settings & Configuration
**Goal:** Manage API keys and simple app constants without editing code.

**V1 Context:** Sidebar inputs for Savings Goal, Date Ranges, etc.
**V2 Improvement:** Persist these in a `Settings` table or JSON file.

**Prompt to Copy:**
```text
I need a Settings page (`ui/pages/settings.py`) to manage app configuration.

1.  **Storage:** Create a simple `KeyValueStore` model in the DB (key, value) OR use a `config.json` managed by a service.
2.  **Fields to Manage:**
    *   `Savings Goal` (Monthly target).
    *   `Gemini API Key` (if not using env vars).
    *   `SimpleFin Token`.
3.  **UI:** Simple form with "Save" button. These values should influence the Dashboard calculations (e.g., Progress towards Goal).
```

---

## Step 10: "Clean Data" / Metadata Tab
**Goal:** V1 had a tab showing "Unmapped Descriptions" and raw data stats.

**V1 Context:** Metrics showing "Unmapped Descriptions", "Unique Descriptions".
**V2 Improvement:** This is a "Health Check" dashboard.

**Prompt to Copy:**
```text
I need a Data Health Dashboard component.

1.  **Metrics:** Query the DB for:
    *   Count of `Uncategorized` transactions.
    *   Count of transactions with `is_excluded=False`.
    *   Last Import Date.
2.  **UI:** Display these as "Cards" at the top of the Import page or Dashboard.
    *   If `Uncategorized > 0`, show a warning color and a link to the AI tool.
```
