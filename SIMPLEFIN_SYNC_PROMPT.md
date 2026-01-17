# SimpleFin Sync & Staging Feature Prompt

Use this prompt to build the SimpleFin integration in `Fin_App_V2`.

**Goal:** Implement a "Bank Sync" feature that fetches transactions from SimpleFin, places them in a "Staging Area" (database table) for review, and allows the user to approve them into the main `Transaction` table. This replaces the direct-load approach from V1.

---

## Part 1: Database Schema

**Prompt to Copy:**
```python
I need to add a "Staging" table to `database/models.py` to hold transactions fetched from SimpleFin before they are approved.

Please add the following model:

class StagedTransaction(Base):
    __tablename__ = 'staged_transactions'
    
    id = Column(Integer, primary_key=True)
    external_id = Column(String, unique=True) # The unique ID from SimpleFin (account_id + transaction_id)
    date = Column(DateTime)
    description = Column(String) # The raw description
    amount = Column(Float)
    account_name = Column(String) # e.g. "Chase - Checking"
    status = Column(String, default="pending") # "pending", "approved", "rejected"
    
    # Metadata
    fetched_at = Column(DateTime, default=datetime.utcnow)

# Database Migration
# Ensure this table is created in `main.py` or your migration script.
```

---

## Part 2: SimpleFin Service (Backend)

**Prompt to Copy:**
```python
Create a new service file `services/simplefin.py`. This service will handle the API communication with SimpleFin.

It needs to implement the logic found in the V1 app, specifically:
1.  **Claim Token:** A function `claim_setup_token(setup_token)` that posts to `https://bridge.simplefin.org/simplefin/claim` to get the Access URL.
2.  **Fetch Transactions:** A function `fetch_transactions(access_url, start_date, end_date)` that:
    *   Uses Basic Auth (username/password parsed from the Access URL).
    *   **Handles Pagination:** SimpleFin has a 60-day limit per request. You MUST implement a loop that fetches data in 50-day chunks if the requested range is larger (e.g., "Last 2 Years").
    *   Merges accounts and transactions from the paginated responses.
3.  **Data Cleaning:**
    *   Helper function `clean_description(desc)`:
        ```python
        def clean_description(desc):
            desc = str(desc).upper()
            desc = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', desc) # Remove dates
            desc = re.sub(r'#?\d{4,}', '', desc) # Remove long IDs
            desc = re.sub(r'STORE\s*\d+', '', desc) # Remove Store #
            return desc.strip()
        ```

Dependencies: `requests`, `urllib.parse`, `base64`.
```

---

## Part 3: Synchronization Logic (Staging)

**Prompt to Copy:**
```python
Create a "Sync Manager" function in `services/sync_manager.py` (or add to `importer.py`) that orchestrates the data flow.

Function: `sync_simplefin_to_staging(access_url, lookback_days=30)`

Logic:
1.  Calculate `start_date` based on lookback.
2.  Call `simplefin.fetch_transactions`.
3.  Iterate through the fetched transactions.
4.  **Hard Cutoff Date:**
    *   **CRITICAL Requirement:** Discard any transaction where `date < 2026-01-01`. SimpleFin is exclusively for new data; historical data (pre-2026) is handled via CSV import.
5.  **Deduplication Check:**
    *   Construct a unique `external_id` (e.g., `f"{account_id}-{transaction_id}"`).
    *   Check if this `external_id` ALREADY exists in the main `Transaction` table. If yes, **SKIP IT** (it's already done).
    *   Check if it exists in `StagedTransaction`. If yes, skip (or update).
6.  **Insert:** If new, insert into `StagedTransaction` with `status='pending'`.
7.  Return stats: "X fetched, Y new staged, Z skipped".
```

---

## Part 4: UI - Bank Sync & Review Page

**Prompt to Copy:**
```python
Create a new page `ui/pages/bank_sync.py`.

**Section 1: Configuration**
*   Input field for "SimpleFin Setup Token".
*   Button "Claim & Save" (calls `claim_setup_token` and saves the resulting URL to a persistent storage, e.g., local file or a Settings table).
*   Dropdown for "History Depth" (1 month, 1 year, etc).
*   Button "Sync Now".
    *   On click, run `sync_simplefin_to_staging`.
    *   Show a notification with the results.

**Section 2: Staging Review (The "Inbox")**
*   Use `ui.aggrid` to show all `StagedTransaction` records where `status == 'pending'`.
*   Columns: Date, Account, Description, Amount.
*   **Checkbox Selection:** Allow selecting multiple rows.
*   **Action Buttons:**
    *   **"Approve Selected":**
        1.  Reads selected rows.
        2.  Moves them to the main `Transaction` table.
        3.  **IMPORTANT:** Run the `MerchantMap` (Renaming) and `CategoryMap` (Auto-Categorization) logic on these transactions AS they are moved.
        4.  Deletes them from `StagedTransaction`.
        5.  Refreshes the grid.
    *   **"Reject Selected":**
        1.  Deletes them from `StagedTransaction` (or marks as 'rejected' if you want history).
```
