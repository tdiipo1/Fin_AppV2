# FinApp V2: Migration & Initialization Guide

## 🤖 Initialization Prompt
**Copy and paste this into the AI Chat when you open the `Fin_App_V2` workspace:**

```text
I am building "FinApp V2", a local-first personal finance application using Python.
Stack: NiceGUI (Frontend), SQLAlchemy + SQLite (Backend), Pandas (Data Processing).

Current State:
- The project structure is created.
- `main.py` initializes the NiceGUI server.
- `database/models.py` defines the basic `Transaction` schema.
- `services/importer.py` handles CSV normalization.
- `services/backup.py` handles daily backups.

My Goal:
I need to port the complete feature set from my legacy Streamlit application (V1) to this new architecture.

Here is the prioritized implementation roadmap we need to execute:
1. **Taxonomy System**: Create a `Category` and `Subcategory` table in the DB and a script to seed them from a CSV (Section -> Category -> Subcategory).
2. **Transaction Management**: Implement a full AG Grid in `ui/pages/transactions.py` that allows editing categories inline and deleting rows.
3. **AI Integration**: Create `services/ai.py` to connect to Google Gemini. It should fetch `Uncategorized` transactions from the DB, generate a prompt, and update their categories.
4. **Dashboard**: Port the Plotly charts from V1 into `ui/pages/dashboard.py` (Net Worth, Monthly In/Out, Category breakdown).
5. **SimpleFin Sync**: Create `services/simplefin.py` to fetch transactions from the SimpleFin Bridge API and merge them using the existing fingerprinting logic.

Let's start with step 1: The Taxonomy System. Content references are available in `MIGRATION_PLAN.md`.
```

---

## 📋 V1 Features to Build in V2 (Detailed Steps)

### 1. Taxonomy & Categories (The Backend Structure)
**V1 Context:** Used a CSV (`Sections_category_subcategory.csv`) to define the hierarchy.
**V2 Implementation:**
*   **Database:** Create `Category` model in `database/models.py`.
    *   Columns: `id`, `section`, `category_name`, `subcategory_name`.
*   **Seeding:** Create a utility `services/taxonomy.py`:
    *   Function `load_master_taxonomy(csv_path)`: Reads the CSV and populates the SQLite table if empty.
*   **Relationship:** Update `Transaction` model to link to `Category` (Foreign Key) or store the normalized string name. Link is better for renaming.

### 2. Transaction Management (The Data Grid)
**V1 Context:** Used `st.data_editor` to show rows.
**V2 Implementation:**
*   **UI:** In `ui/pages/transactions.py`, use `ui.aggrid`.
*   **Features:**
    *   **Pagination:** Load 100 rows at a time or use infinite scroll (NiceGUI handles this well).
    *   **Filtering:** Use AG Grid's built-in filtering for "Date", "Amount", "Description".
    *   **Editing:** When a user changes a cell in AG Grid, trigger an event to update the SQLite record via `session.commit()`.
    *   **Delete:** Add a "trash can" button column.

### 3. AI Normalization (Brain of the App)
**V1 Context:** `st.sidebar` settings sent prompts to Gemini to map "Raw Description" -> "Clean Description" + "Category".
**V2 Implementation:**
*   **Service:** `services/ai.py`.
*   **Logic:**
    1.  Query DB: `SELECT * FROM transactions WHERE category = 'Uncategorized'`.
    2.  Batch: Group into chunks of 50.
    3.  Prompt: "Map these descriptions to the following categories: [List of Categories]".
    4.  Update: Write results back to DB.
*   **UI:** In `ui/pages/import_page.py` or a new `ui/pages/ai.py`, add a button "Run AI Normalization". Show a progress bar (`ui.linear_progress`).

### 4. Interactive Dashboard (Visuals)
**V1 Context:** Plotly charts for Income vs Expenses, Net Worth over time.
**V2 Implementation:**
*   **Data Fetching:** Do **not** load all data into Pandas every time. Use SQL aggregations:
    *   `SELECT strftime('%Y-%m', date) as month, SUM(amount) FROM transactions GROUP BY month`.
*   **Rendering:** Use `ui.plotly(fig)`.
    *   *Chart 1:* Monthly Bar Chart (Inflow Green / Outflow Red).
    *   *Chart 2:* Line Chart (Running Total / Net Worth).
    *   *Chart 3:* Sankey Diagram or Sunburst for Section -> Category -> Subcategory flow.

### 5. SimpleFin Connectivity (Live Data)
**V1 Context:** User intention (wasn't fully present in the snippet provided).
**V2 Implementation:**
*   **Config:** Store SimpleFin Access URL in `.env` (managed by `python-dotenv`).
*   **Service:** `services/simplefin.py`.
    *   `fetch_transactions(start_date, end_date)`: Returns list of transaction dicts.
*   **Merging:** Pass these dicts to the **Importer** service which already has the `fingerprint` logic. This ensures that if SimpleFin sends a transaction you already imported via CSV, it won't duplicate.

### 6. Merchant Intelligence (Deep Dive)
**V1 Context:** Aggregated spending by Merchant.
**V2 Implementation:**
*   **SQL View:** `SELECT clean_description, SUM(amount), COUNT(*) FROM transactions GROUP BY clean_description ORDER BY SUM(amount) ASC`.
*   **UI:** A drill-down view. Clicking a merchant in the list opens a dialog (`ui.dialog`) showing history for that specific merchant.
