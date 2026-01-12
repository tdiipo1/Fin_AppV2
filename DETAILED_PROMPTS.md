# Detailed Implementation Prompts

Use these prompts one by one in your new `Fin_App_V2` workspace to build out the features.

## Step 1: Database Schema & Initial Data Load
**Goal:** Update the database to hold your Taxonomy, Mappings, and Budget, then create a script to load the CSVs you currently have.

**Prompt to Copy:**
```text
I need to update `database/models.py` to support the full data structure of my application.
Please add the following SQLAlchemy models:

1.  **Category** (Taxonomy)
    *   Columns: `id` (String, Primary Key, e.g. "SCSC0001"), `section`, `category`, `subcategory`.
2.  **MerchantMap** (Renaming Rules)
    *   Columns: `id` (Integer PK), `raw_description`, `standardized_merchant`.
3.  **CategoryMap** (AI Rules)
    *   Columns: `id` (Integer PK), `unmapped_description`, `scsc_id` (ForeignKey to Category.id).
4.  **Budget** (Targets)
    *   Columns: `id` (Integer PK), `scsc_id` (ForeignKey to Category.id), `amount`.
    *   Note: The CSV has Section/Category columns too, but we only strictly need `scsc_id` and `amount` linked to the Category table.

After updating the models, please write a script `services/seed_data.py` to populate these tables from my existing CSV files:
1.  `Sections_category_subcategory.csv` -> **Category** table. (Cols: ID, Section, Category, Subcategory)
2.  `merchant_map.csv` -> **MerchantMap** table. (Cols: Raw_Description, Standardized_Merchant)
3.  `ChatGPT_normalization_map_ID.csv` -> **CategoryMap** table. (Cols: Unmapped_Description, SCSC_ID)
4.  `budget.csv` -> **Budget** table. (Cols: SCSC_ID, Amount)

The script should check if data exists before adding to avoid duplicates, or use `INSERT OR REPLACE`.
```

---

## Step 2: Transaction Import & Manual Upload
**Goal:** Create a UI page where you can upload your legacy CSV files (transactions) and have them inserted into the database with the correct mapped categories.

**Prompt to Copy:**
```text
Now let's build the **Import** feature.
1.  Update `services/importer.py`:
    *   It should accept a pandas DataFrame.
    *   It needs to apply the `MerchantMap` (Raw -> Standardized) and `CategoryMap` (Description -> SCSC_ID) logic *before* saving to the DB.
    *   If a row matches a `CategoryMap` entry, assign the corresponding `category_id` (SCSC code).
    *   Use the existing fingerprinting logic to prevent duplicates.

2.  Update `ui/pages/import_page.py`:
    *   Create a drag-and-drop area for CSV files.
    *   Add a "Process Import" button.
    *   When clicked, run the importer and show a notification of how many new records were added.
```

---

## Step 3: Transaction Management (AG Grid)
**Goal:** A powerful table to view, edit, and categorize transactions manually.

**Prompt to Copy:**
```text
I need to build the `ui/pages/transactions.py` page using NiceGUI's `ui.aggrid`.

Requirements:
1.  **Data Source:** Query all `Transaction` records from the DB, joining with the `Category` table to get the Section/Category names.
2.  **Columns:** Date, Merchant (Raw), Merchant (Clean), Amount, Category (Dropdown), Section (Read-only), Source.
3.  **Inline Editing:**
    *   Allow editing `Clean Description`.
    *   Allow changing `Category` via a dropdown selector (populated from the `Category` table).
    *   When a cell is edited, update the database immediately.
4.  **Delete:** Add a button/icon to delete a row.
5.  **Selection:** Allow multi-select to delete multiple rows.
```

---

## Step 4: Dashboard & Budgeting
**Goal:** Recreate the Plotly charts and budget comparison.

**Prompt to Copy:**
```text
Let's build the Dashboard in `ui/pages/dashboard.py`.

1.  **Data Aggregation:** Write a function in `services/analytics.py` that queries the database using SQL to get:
    *   Monthly Net Income (Inflow vs Outflow).
    *   Spending by Section/Category for the current month.
    *   DB-side comparision of `Actual Spending` (Transaction Sum) vs `Budget` (from Budget table).

2.  **Budget Progress:**
    *   Display a progress bar for each Major Section (e.g., "Dining", "Shopping").
    *   Show "Spent X / Y Budgeted".

3.  **Visuals:**
    *   Use `ui.plotly` to render a Bar chart for Monthly Income/Expense.
    *   Use `ui.plotly` to render a Sunburst chart for the Category breakdown.
```

---

## Step 5: AI Normalization Service
**Goal:** Connect Gemini to fill in the gaps for transactions that were missed by your manual CSS maps.

**Prompt to Copy:**
```text
I need to implement the AI service in `services/ai.py` using `google-generativeai`.

1.  **Fetch:** Create a function to get all `Transaction` records where `category_id` is NULL.
2.  **Prompt Generation:**
    *   Create a prompt that lists the unique descriptions and asks Gemini to map them to the SCSC_IDs found in the `Category` table.
    *   Limit the batch size to 50 items per request.
3.  **Processing:**
    *   Parse the JSON response from Gemini.
    *   Update the `Transaction` table with the new `category_id`.
    *   **Crucial:** Also save this new rule to the `CategoryMap` table so future imports happen automatically without AI.
4.  **UI:** Add a "Auto-Categorize with AI" button in the Settings or Import page.
```
