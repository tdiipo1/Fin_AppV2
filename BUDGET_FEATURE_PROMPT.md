# Budget Feature Implementation Prompt for Version 2

## Overview
The Budget feature in Version 1 allows users to:
1. **Upload a Budget CSV** containing structured category allocations
2. **View categories hierarchically** (Section > Category > Subcategory)
3. **Edit budget amounts** interactively with live updates
4. **Calculate baselines** from historical spending (last 12 months)
5. **Track surplus/deficit** against "Available Money"
6. **Compare actual spending vs budget** in a Spending Report tab
7. **Persist changes** across sessions via browser localStorage and/or disk exports

For Version 2, this will move to a **relational database structure** instead of CSV-only, while maintaining the ability to **bulk import CSVs**.

---

## Data Structure (Database Schema)

### 1. **Budget Table**
Stores allocated budget amounts for each category.

**Columns:**
- `id` (Integer, Primary Key)
- `scsc_id` (String, Foreign Key → Category.id)
- `amount` (Float) - Budget amount in dollars
- `created_at` (DateTime) - Timestamp of creation
- `updated_at` (DateTime) - Timestamp of last modification
- `note` (Text, optional) - User note or memo

**Relationships:**
- Belongs to `Category` via `scsc_id`

**Indexing:**
- `scsc_id` (for quick lookups when comparing actual vs budget)

---

### 2. **Category Table** (Existing from Step 1)
Hierarchical taxonomy for budgeting.

**Columns:**
- `id` (String, Primary Key, e.g., "SCSC0001")
- `section` (String) - Top-level grouping (e.g., "Housing", "Food & Dining")
- `category` (String) - Mid-level (e.g., "Groceries")
- `subcategory` (String) - Leaf level (e.g., "Whole Foods")

---

## Feature 1: Budget CSV Import & Bulk Load

### Sidebar UI Component (`ui/components/budget_import.py`)

```
User Flow:
1. User clicks "Upload Budget CSV" file uploader in sidebar
2. System detects CSV format:
   - Schema A: SCSC_ID, Section, Category, Subcategory, Amount
   - Schema B: Section, Category, Subcategory, Amount (resolve SCSC_ID via Category table)
3. System validates:
   - All rows have SCSC_ID that exist in Category table
   - Amount column is numeric and >= 0
   - No duplicate entries (Section, Category, Subcategory)
4. System shows preview:
   - "Row Count: X rows will be imported"
   - "New entries: Y rows (not in DB)"
   - "Updated entries: Z rows (existing SCSC_ID)"
5. User clicks "Import to Database"
   - For each row, insert or update Budget record
   - Log changes for audit trail
6. System shows confirmation:
   - "Budget imported: X records inserted, Y records updated"
```

### Backend Logic (`services/budget_service.py`)

**Function: `import_budget_csv(file_path: str, user_id: int, dry_run: bool = False) -> dict`**

Input:
- Pandas DataFrame with columns: `SCSC_ID` (or `Section/Category/Subcategory`) and `Amount`
- User ID (for audit trail)
- Dry-run flag (preview without commit)

Process:
1. **Detect Schema:**
   - Look for `SCSC_ID` column
   - If missing, try to resolve via `(Section, Category, Subcategory)` lookup in Category table
   - If can't resolve, mark row as "unmatched" and skip or warn

2. **Validate Data:**
   - Convert `Amount` to float, reject non-numeric values
   - Check SCSC_ID exists in Category table
   - Flag duplicates within the CSV (keep first, warn about duplicates)

3. **Check Existing:**
   - Query Budget table for existing entries matching SCSC_ID
   - Determine insert vs update for each row

4. **Execute (if not dry_run):**
   - Use `INSERT OR REPLACE` (SQLite) / `ON CONFLICT` (PostgreSQL) to avoid duplicate key errors
   - Record each insert/update with `updated_at` timestamp
   - Log to an audit trail table if available

Output:
```python
{
    "success": bool,
    "total_rows": int,
    "inserted": int,
    "updated": int,
    "skipped": int,
    "errors": [{"row": int, "scsc_id": str, "reason": str}],
    "warnings": [str],
    "preview": DataFrame (if dry_run=True)
}
```

---

## Feature 2: Budget Planning Tab (Interactive Editor)

### UI Component (`ui/pages/budget_planning.py`)

**Layout:**

```
[Header: 💰 Budget Planning]

[Expand All] [Collapse All] [Reset to Database] [Live Updates ☑️]

Available Money: [INPUT: $0.00]                   Surplus: $0.00

[TAB: Browse by Category]
  Section 1: Housing (5 categories)
    ├─ Category: Rent
    │  Amount: $2,000  [EDIT → $2,000]
    ├─ Category: Utilities
    │  Amount: $150    [EDIT → $150]
    └─ ...

[TAB: Upload CSV]
  [Drag & drop or click to upload CSV]
  Schema: SCSC_ID, Section, Category, Subcategory, Amount

[Download Current Budget as CSV]
[Save Changes to Database]
```

### Interactive Features

**1. Hierarchical Accordion View**
- Group budget entries by Section
- Each Section expander shows count of categories
- Expand/Collapse individual sections or all at once
- Remember open/closed state per session (optional: persist to DB as user preference)

**2. Inline Editing**
- Display budget amount in a number input field
- User can modify value directly
- Two modes:
  - **Live Updates:** Save to session state immediately on input change, no save button
  - **Buffered:** Collect changes, show single "Save" button at bottom

**3. Available Money & Surplus Indicator**
- Input field: "Available Money" (e.g., monthly income or total budget pool)
- Auto-calculate: `Surplus = Available Money - Total Budgeted`
- Display in real-time with color coding:
  - Green if surplus >= 0
  - Red if deficit < 0
- Show breakdown by Section

**4. Baseline Calculation**
- If a budget amount is 0 or missing, show historical baseline from actual spending
- Baseline source: Query actual spending from Transaction table for last 12 months, grouped by SCSC_ID
- Display as placeholder/suggestion (user can override)
- Helpful for first-time budget creation

**5. Reset Functionality**
- "Reset to Database" button clears all user edits and reloads from DB
- Confirmation dialog: "This will discard unsaved changes. Continue?"

---

## Feature 3: Budget-to-Actual Comparison (Spending Report)

### UI Component (`ui/pages/spending_report.py` - Enhanced)

**Purpose:** Compare actual spending (from Transaction table) vs budgeted amounts (from Budget table)

**Data Flow:**

```
1. Query Database:
   - SELECT SUM(Amount) FROM Transaction WHERE Amount < 0 AND Date >= start_date AND Date <= end_date, grouped by scsc_id
   - SELECT amount FROM Budget, grouped by scsc_id

2. Merge:
   - FULL OUTER JOIN on scsc_id
   - Calculate: Variance = Budget - Actual

3. Render:
   - Table: Section | Category | Budgeted | Actual | Variance | Variance % | Status
   - Charts: Budget vs Actual (grouped bar), Variance by category (sorted), Actual spend distribution (pie)
   - Drill-down: Click category → show all transactions for that category
```

**Features:**

**1. Summary Metrics**
```
┌─────────────────────────────────────────┐
│ Total Budgeted: $X,XXX                  │
│ Total Spent: $Y,YYY                     │
│ Total Variance: $Z,ZZZ (% of budget)   │
│ Over Budget: N categories               │
│ Under Budget: M categories              │
└─────────────────────────────────────────┘
```

**2. Comparison Table**
Columns: Section, Category, Budgeted ($), Actual ($), Variance ($), Variance (%), Status (🟢 On-track / 🟡 Caution / 🔴 Over)

Sorting:
- By Variance amount (largest first)
- By Variance % (highest risk)
- By Category name

**3. Interactive Charts**
- **Budget vs Actual (Grouped Bar):** Shows two bars per category for easy comparison
- **Variance by Category (Horizontal Bar):** Sorted by variance, color-coded (green = under, red = over)
- **Actual Spend Distribution (Pie/Donut):** Shows % of total spending by category

**4. Drill-Down by Category**
```
Select Category: [Dropdown of all categories]

Transactions for [Category Name] (X transactions):
┌──────────┬──────────────────┬──────────┬──────────┐
│ Date     │ Description      │ Amount   │ Source   │
├──────────┼──────────────────┼──────────┼──────────┤
│ 2025-01-15 | Whole Foods    | -$45.30  | Chase    │
│ 2025-01-18 | Trader Joe's   | -$32.15  | Discover │
│ ...      │ ...              │ ...      │ ...      │
└──────────┴──────────────────┴──────────┴──────────┘
```

---

## Feature 4: Auto-Calculation of Baselines

### Backend Logic (`services/analytics.py`)

**Function: `calculate_category_baselines(months: int = 12) -> dict`**

Input:
- Number of months to look back (default: 12 for full year)

Process:
1. **Query Transactions:**
   ```sql
   SELECT scsc_id, SUM(ABS(amount)) as spend
   FROM Transaction
   WHERE amount < 0  -- expenses only
   AND date >= NOW() - INTERVAL '12 months'
   GROUP BY scsc_id
   ```

2. **Fill Missing:**
   - For categories in Category table with zero spending, return 0
   - For categories with spending but no budget yet, mark as "unbudgeted"

3. **Return:**
   ```python
   {
       "SCSC0001": 1500.00,  # Groceries spending
       "SCSC0002": 200.00,   # Dining out
       ...
   }
   ```

**Usage in Budget Planning UI:**
- When editing a category with $0 budget, show baseline as placeholder
- User can click "Use Baseline" button to populate from historical average
- Or user can manually enter custom amount

---

## Feature 5: Persistence & State Management

### Session State (In-Memory)

```python
st.session_state = {
    'budget_dict': {
        'Housing': 2150,
        'Food & Dining': 800,
        ...
    },
    'budget_amounts': {
        'Housing::Rent::': 2000,
        'Housing::Utilities::': 150,
        ...
    },
    'available_money': 5000.00,
    'budget_open_sections': ['Housing', 'Food & Dining'],
}
```

### Database Persistence

1. **Budget Table:**
   - All budget amounts are immediately saved to `Budget` table on import or edit
   - Each row has `updated_at` timestamp for change tracking

2. **User Preferences (Optional):**
   - Create `BudgetPreference` table:
     - `user_id`, `key` (e.g., "available_money"), `value` (JSON)
     - Store "Available Money", "Open Sections", "Live Update Mode"

3. **Audit Trail (Optional):**
   - Create `BudgetAuditLog` table:
     - `id`, `user_id`, `scsc_id`, `old_amount`, `new_amount`, `action` (import/manual edit), `timestamp`
     - Track all budget changes for accountability

---

## Feature 6: CSV Export & Download

### UI Controls

```
[Download Current Budget as CSV]
[Download Spending Report as CSV]
```

### Export Formats

**Budget CSV:**
```
SCSC_ID,Section,Category,Subcategory,Amount,Updated_At
SCSC0001,Housing,Rent,,2000.00,2025-01-11 10:30:00
SCSC0002,Housing,Utilities,,150.00,2025-01-10 15:45:00
...
```

**Spending Report CSV:**
```
Section,Category,Budgeted,Actual,Variance,Variance_Percent,Status
Housing,Rent,2000.00,1950.50,49.50,2.5%,On-track
Housing,Utilities,150.00,165.00,-15.00,-10.0%,Over
...
```

---

## Feature 7: Multi-User Support (Future)

**Current Scope:** Single-user or basic multi-user (user_id in Budget table)

**Fields to Add:**
- `Budget.created_by` (user_id)
- `Budget.updated_by` (user_id)
- `Budget.is_shared` (bool, for future team budgets)

**Permissions:**
- Users can only see/edit their own budgets (or shared budgets)
- Admins can view all budgets

---

## Implementation Checklist

### Phase 1: Core Budget Management
- [ ] Create Budget model in `database/models.py`
- [ ] Write `services/budget_service.py` with import/export logic
- [ ] Build `ui/pages/budget_planning.py` with interactive editor
- [ ] Connect Budget table to Category table via SCSC_ID

### Phase 2: Comparison & Analytics
- [ ] Enhance `services/analytics.py` with budget-to-actual queries
- [ ] Build `ui/pages/spending_report.py` with comparison charts
- [ ] Add drill-down transaction filtering

### Phase 3: Persistence & Preferences
- [ ] Add BudgetPreference table (optional)
- [ ] Implement user preference save/load
- [ ] Add export CSV/download buttons

### Phase 4: Advanced Features
- [ ] Budget history & audit trail
- [ ] Baseline calculation auto-populator
- [ ] Multi-user budget sharing
- [ ] Budget forecasting (next month prediction based on trend)

---

## Key Implementation Notes

1. **SCSC_ID Hierarchy:** All budget entries MUST be linked to the SCSC_ID in the Category table. This ensures consistency with transaction categorization.

2. **CSV Bulk Import:** Always validate SCSC_ID or resolve from Section/Category/Subcategory BEFORE inserting. Skip invalid rows with clear error messages.

3. **Live vs Buffered Edits:** Use a session state flag to toggle between:
   - Live: Save to DB on every input change
   - Buffered: Collect changes, save on single "Save" button click

4. **Baseline Calculation:** Should be optional and shown as a suggestion/placeholder. User decides whether to adopt it.

5. **Available Money:** A user-defined pool (e.g., monthly income). Not stored per category, but at the top level. Use for overall surplus/deficit calculation.

6. **Variance Sign Convention:** 
   - Positive variance = Under budget (good) 🟢
   - Negative variance = Over budget (caution) 🔴

7. **Performance:** For large datasets (1000+ categories), use database-side aggregation (SQL SUM, GROUP BY) rather than loading all rows into Python.

8. **UI Polish:** Group categories by Section in accordions to avoid overwhelming users with too many inputs. Show count of items per section.

---

## Example CSV Formats

### Input CSV (for bulk import):
```
SCSC_ID,Amount
SCSC0001,2000
SCSC0002,150
SCSC0003,800
```

Or (if SCSC_ID unknown):
```
Section,Category,Subcategory,Amount
Housing,Rent,,2000
Housing,Utilities,,150
Food & Dining,Groceries,,800
```

### Output CSV (export):
```
SCSC_ID,Section,Category,Subcategory,Amount,Updated_At
SCSC0001,Housing,Rent,,2000.00,2025-01-11 10:30:00
SCSC0002,Housing,Utilities,,150.00,2025-01-10 15:45:00
SCSC0003,Food & Dining,Groceries,,800.00,2025-01-09 12:00:00
```

---

## Questions for Clarification

1. Should budget amounts be rounded to nearest $1, $10, or allow cents?
2. Should we support monthly budgets only, or also weekly/quarterly/annual?
3. Should we allow negative budgets (e.g., income targets)?
4. Should deleting a budget record from DB also delete associated transactions? (Answer: NO, keep transactions, just remove budget target)
5. Should we track budget history (e.g., "budget was $X on this date, now $Y")? (Optional for audit trail)
