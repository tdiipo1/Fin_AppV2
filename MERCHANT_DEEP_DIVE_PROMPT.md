# Merchant Deep Dive & Merchant Intelligence - Comprehensive Feature Prompt for Version 2

## Executive Overview

The "Merchant Deep Dive" and "Merchant Intelligence" features in Version 1 are powered by a sophisticated data enrichment pipeline that:

1. **Standardizes raw merchant names** (from bank transactions) → **Standardized Merchant Names** via a merchant mapping CSV
2. **Categorizes standardized merchants** into a hierarchical taxonomy (Section > Category > Subcategory) via a normalization/category mapping CSV
3. **Aggregates and visualizes** spending by merchant, category, and trends using multiple chart types
4. **Enables drill-downs** to view transaction-level details and historical trends for a specific merchant

In Version 2, all of this functionality moves from **CSV-based** to **database-driven** while maintaining the ability to **bulk import CSVs** to populate and update the database. This prompt outlines the complete data architecture, database schema, analytics pipeline, and UI components needed to replicate and enhance this feature.

---

## Part 1: Data Architecture & CSV Sources

### Current V1 CSV Dependencies

#### 1. **Merchant Mapping CSV** (`merchant_map.csv`)
Maps raw transaction descriptions to standardized merchant names.

**Purpose:** Normalize messy bank descriptions (e.g., "WHOLE FOODS MKT #2341" → "Whole Foods")

**Current Schema:**
```
Raw_Description,Standardized_Merchant
WHOLE FOODS MKT #2341,Whole Foods
WHOLE FOODS MKT #5621,Whole Foods
SAFEWAY #123,Safeway
SAFEWAY #456,Safeway
SHELL OIL #789,Shell Gas
...
```

**Characteristics:**
- One-to-many mapping (multiple raw descriptions map to one standardized name)
- Case variations and abbreviations in raw descriptions
- Store numbers, location codes stripped out
- Manual curation and expansion over time

---

#### 2. **Category/Normalization Mapping CSV** (`ChatGPT_normalization_map_ID.csv`)
Maps standardized merchant names (and sometimes raw descriptions) to SCSC_ID (Section-Category-Subcategory IDs).

**Purpose:** Assign a hierarchical category to each standardized merchant

**Current Schema:**
```
Unmapped_Description,SCSC_ID
Whole Foods,SCSC0034
Safeway,SCSC0034
Trader Joe's,SCSC0034
Shell Gas,SCSC0061
Chevron,SCSC0061
McDonald's,SCSC0045
Starbucks,SCSC0046
...
```

**Characteristics:**
- Many-to-one relationship (multiple merchants map to one SCSC_ID)
- SCSC_ID is the primary key linking to the Category taxonomy
- Unmapped_Description can be either raw or standardized merchant names
- AI-generated (via Gemini) or manually curated

---

#### 3. **Category Taxonomy CSV** (`Sections_category_subcategory.csv`)
The authoritative taxonomy defining all valid categories.

**Purpose:** Define the hierarchical structure for all budgets and analytics

**Current Schema:**
```
ID,Section,Category,Subcategory
SCSC0001,Housing,Rent,,
SCSC0002,Housing,Utilities,Electric
SCSC0003,Housing,Utilities,Water
SCSC0034,Food & Dining,Groceries,Supermarket
SCSC0045,Food & Dining,Dining Out,Fast Food
SCSC0046,Food & Dining,Dining Out,Coffee
SCSC0061,Transportation,Gas,Major Brand
...
```

**Characteristics:**
- Single source of truth for all categories
- 4-level hierarchy: ID → Section → Category → Subcategory
- Subcategory can be empty (leaf level varies)
- Used in budgeting, reporting, and analytics

---

### V1 Data Flow Diagram

```
Raw Bank Transaction
  ↓
Clean_Description (via regex cleaning)
  ↓
Look up in Merchant Mapping CSV
  ↓
Standardized_Merchant (e.g., "Whole Foods")
  ↓
Look up Standardized_Merchant in Normalization CSV
  ↓
SCSC_ID (e.g., "SCSC0034")
  ↓
Look up SCSC_ID in Category Taxonomy
  ↓
Section, Category, Subcategory (e.g., "Food & Dining", "Groceries", "Supermarket")
  ↓
Enriched Transaction with all metadata
  ↓
Analytics & Visualization
```

---

## Part 2: Database Schema Design

### New Tables for Version 2

#### 1. **MerchantMap Table**
Replaces the merchant_map.csv in the database.

```sql
CREATE TABLE merchant_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_description TEXT NOT NULL UNIQUE,
    standardized_merchant TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_raw_description ON merchant_map(raw_description);
CREATE INDEX idx_standardized_merchant ON merchant_map(standardized_merchant);
```

**Purpose:** Fast lookup from raw bank description to standardized merchant name

**Data Example:**
```
id | raw_description            | standardized_merchant | created_at            | updated_at | is_active
1  | WHOLE FOODS MKT #2341      | Whole Foods          | 2025-01-01 10:00:00  | 2025-01-01 | 1
2  | WHOLE FOODS MKT #5621      | Whole Foods          | 2025-01-01 10:00:00  | 2025-01-01 | 1
3  | SAFEWAY #123               | Safeway              | 2025-01-01 10:00:00  | 2025-01-01 | 1
4  | SHELL OIL #789             | Shell Gas            | 2025-01-01 10:00:00  | 2025-01-01 | 1
```

---

#### 2. **CategoryMap Table** (Enhanced from Step 1)
Replaces the normalization_map.csv in the database.

```sql
CREATE TABLE category_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unmapped_description TEXT NOT NULL UNIQUE,
    scsc_id TEXT NOT NULL,
    source TEXT DEFAULT 'manual',  -- 'manual', 'ai', 'import'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (scsc_id) REFERENCES category(id)
);

CREATE INDEX idx_unmapped_description ON category_map(unmapped_description);
CREATE INDEX idx_scsc_id ON category_map(scsc_id);
```

**Purpose:** Fast lookup from standardized merchant name (or raw description) to SCSC_ID

**Data Example:**
```
id | unmapped_description | scsc_id  | source | created_at | updated_at | is_active
1  | Whole Foods          | SCSC0034 | ai     | 2025-01-01 | 2025-01-01 | 1
2  | Safeway              | SCSC0034 | ai     | 2025-01-01 | 2025-01-01 | 1
3  | Shell Gas            | SCSC0061 | manual | 2025-01-01 | 2025-01-01 | 1
4  | McDonald's           | SCSC0045 | ai     | 2025-01-01 | 2025-01-01 | 1
```

---

#### 3. **Category Table** (Existing from Step 1)
The authoritative taxonomy.

```sql
CREATE TABLE category (
    id TEXT PRIMARY KEY,  -- e.g., "SCSC0034"
    section TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_section ON category(section);
CREATE INDEX idx_category ON category(category);
```

**Data Example:**
```
id       | section        | category      | subcategory
SCSC0001 | Housing        | Rent          | (null)
SCSC0034 | Food & Dining  | Groceries     | Supermarket
SCSC0045 | Food & Dining  | Dining Out    | Fast Food
SCSC0061 | Transportation | Gas           | Major Brand
```

---

#### 4. **Transaction Table** (Enhanced)
Transactions enriched with merchant and category metadata.

```sql
CREATE TABLE transaction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    raw_description TEXT NOT NULL,
    clean_description TEXT,
    amount DECIMAL(12, 2) NOT NULL,
    source TEXT,  -- 'Chase', 'Discover', 'SimpleFin', etc.
    
    -- Enrichment fields
    standardized_merchant TEXT,
    merchant_map_id INTEGER,
    scsc_id TEXT,
    category_map_id INTEGER,
    
    -- Metadata
    is_excluded BOOLEAN DEFAULT FALSE,
    fingerprint TEXT,  -- for deduplication
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (merchant_map_id) REFERENCES merchant_map(id),
    FOREIGN KEY (category_map_id) REFERENCES category_map(id),
    FOREIGN KEY (scsc_id) REFERENCES category(id)
);

CREATE INDEX idx_date ON transaction(date);
CREATE INDEX idx_standardized_merchant ON transaction(standardized_merchant);
CREATE INDEX idx_scsc_id ON transaction(scsc_id);
CREATE INDEX idx_is_excluded ON transaction(is_excluded);
CREATE UNIQUE INDEX idx_fingerprint ON transaction(fingerprint);
```

**Data Example:**
```
id  | date       | raw_description      | clean_description | amount  | source | standardized_merchant | scsc_id  | is_excluded
1   | 2025-01-15 | WHOLE FOODS #2341    | Whole Foods       | -45.30  | Chase  | Whole Foods          | SCSC0034 | 0
2   | 2025-01-18 | SAFEWAY #123         | Safeway           | -62.15  | Discover | Safeway             | SCSC0034 | 0
3   | 2025-01-20 | SHELL OIL #789       | Shell Gas         | -55.00  | Chase  | Shell Gas            | SCSC0061 | 0
```

---

### Database Relationships Diagram

```
merchant_map (raw_description → standardized_merchant)
       ↓
Transaction.standardized_merchant ← Transaction.merchant_map_id

category_map (unmapped_description → scsc_id)
       ↓
Transaction.scsc_id ← Transaction.category_map_id
       ↓
category (scsc_id → section, category, subcategory)

Transaction enriched with:
  - standardized_merchant (from merchant_map)
  - section, category, subcategory (from category via scsc_id)
```

---

## Part 3: Data Enrichment Pipeline

### Transaction Import & Enrichment Flow

#### Step 1: Load Raw Transaction
```python
Transaction {
    date: 2025-01-15,
    raw_description: "WHOLE FOODS MKT #2341",
    amount: -45.30,
    source: "Chase"
}
```

#### Step 2: Clean Description (Regex)
```python
clean_description = clean_description_regex(raw_description)
# Result: "Whole Foods"

Transaction {
    ...
    clean_description: "Whole Foods",
    ...
}
```

#### Step 3: Lookup Merchant Map
```python
# Query: SELECT * FROM merchant_map WHERE raw_description LIKE "%{clean_description}%"
# OR: Exact match on clean_description

merchant_map_result = query_merchant_map(clean_description)
# Result: MerchantMap { id: 1, standardized_merchant: "Whole Foods" }

Transaction {
    ...
    standardized_merchant: "Whole Foods",
    merchant_map_id: 1,
    ...
}
```

#### Step 4: Lookup Category Map
```python
# Query: SELECT * FROM category_map WHERE unmapped_description = "Whole Foods"

category_map_result = query_category_map(standardized_merchant)
# Result: CategoryMap { id: 5, scsc_id: "SCSC0034" }

Transaction {
    ...
    scsc_id: "SCSC0034",
    category_map_id: 5,
    ...
}
```

#### Step 5: Lookup Category Details
```python
# Query: SELECT * FROM category WHERE id = "SCSC0034"

category_result = query_category(scsc_id)
# Result: Category { 
#   id: "SCSC0034", 
#   section: "Food & Dining", 
#   category: "Groceries", 
#   subcategory: "Supermarket" 
# }

# These become available as computed/denormalized fields in queries:
Transaction.section = "Food & Dining"
Transaction.category = "Groceries"
Transaction.subcategory = "Supermarket"
```

#### Step 6: Final Enriched Transaction
```python
Transaction {
    id: 1,
    date: 2025-01-15,
    raw_description: "WHOLE FOODS MKT #2341",
    clean_description: "Whole Foods",
    amount: -45.30,
    source: "Chase",
    standardized_merchant: "Whole Foods",
    merchant_map_id: 1,
    scsc_id: "SCSC0034",
    category_map_id: 5,
    is_excluded: False,
    # Computed fields (from category join):
    section: "Food & Dining",
    category: "Groceries",
    subcategory: "Supermarket"
}
```

---

### Backend Service: `services/enrichment_service.py`

```python
def enrich_transaction(transaction: Transaction) -> Transaction:
    """
    Enrich a transaction with merchant mapping and category mapping.
    
    Flow:
    1. Clean raw_description
    2. Lookup in merchant_map
    3. Lookup in category_map
    4. Resolve category details
    """
    
    # Step 1: Clean description
    transaction.clean_description = clean_description_regex(transaction.raw_description)
    
    # Step 2: Merchant mapping
    merchant_record = db.query(MerchantMap).filter(
        or_(
            MerchantMap.raw_description == transaction.raw_description,
            MerchantMap.raw_description.ilike(f"%{transaction.clean_description}%")
        )
    ).first()
    
    if merchant_record:
        transaction.standardized_merchant = merchant_record.standardized_merchant
        transaction.merchant_map_id = merchant_record.id
    else:
        transaction.standardized_merchant = transaction.clean_description  # Fallback
    
    # Step 3: Category mapping (lookup by standardized merchant)
    category_record = db.query(CategoryMap).filter(
        CategoryMap.unmapped_description.ilike(f"%{transaction.standardized_merchant}%")
    ).first()
    
    if category_record:
        transaction.scsc_id = category_record.scsc_id
        transaction.category_map_id = category_record.id
    else:
        transaction.scsc_id = None  # Uncategorized
    
    # Step 4: Resolve category details (via join in query)
    # This happens automatically in query results via relationship
    
    return transaction

def enrich_batch_transactions(transactions: List[Transaction]) -> List[Transaction]:
    """Bulk enrich multiple transactions for performance."""
    # Pre-load all maps into memory
    merchant_maps = db.query(MerchantMap).all()
    category_maps = db.query(CategoryMap).all()
    categories = db.query(Category).all()
    
    # Build lookup dictionaries
    merchant_lookup = {m.raw_description: m for m in merchant_maps}
    category_lookup = {c.unmapped_description: c for c in category_maps}
    cat_details = {c.id: c for c in categories}
    
    # Enrich each transaction
    for txn in transactions:
        txn.clean_description = clean_description_regex(txn.raw_description)
        
        # Merchant lookup
        if txn.raw_description in merchant_lookup:
            m = merchant_lookup[txn.raw_description]
            txn.standardized_merchant = m.standardized_merchant
            txn.merchant_map_id = m.id
        else:
            txn.standardized_merchant = txn.clean_description
        
        # Category lookup
        if txn.standardized_merchant in category_lookup:
            c = category_lookup[txn.standardized_merchant]
            txn.scsc_id = c.scsc_id
            txn.category_map_id = c.id
        
    db.session.add_all(transactions)
    db.session.commit()
    
    return transactions
```

---

## Part 4: CSV Bulk Import & Data Migration

### CSV Import Service: `services/csv_importer.py`

#### Function 1: Import Merchant Map CSV

```python
def import_merchant_map_csv(
    file_path: str,
    user_id: int,
    replace_existing: bool = False,
    dry_run: bool = False
) -> dict:
    """
    Import merchant mapping CSV into merchant_map table.
    
    Expected CSV Columns:
    - raw_description (or 'Raw_Description', 'Description')
    - standardized_merchant (or 'Standardized_Merchant', 'Merchant')
    
    Returns:
    {
        'success': bool,
        'total_rows': int,
        'inserted': int,
        'updated': int,
        'skipped': int,
        'errors': [{'row': int, 'raw_description': str, 'reason': str}],
        'preview': DataFrame (if dry_run=True)
    }
    """
    
    df = pd.read_csv(file_path)
    
    # Detect columns
    cols_lower = {c.lower(): c for c in df.columns}
    raw_col = cols_lower.get('raw_description') or cols_lower.get('description')
    std_col = cols_lower.get('standardized_merchant') or cols_lower.get('merchant')
    
    if not raw_col or not std_col:
        raise ValueError("CSV must contain 'raw_description' and 'standardized_merchant' columns")
    
    errors = []
    inserts = 0
    updates = 0
    skips = 0
    
    for idx, row in df.iterrows():
        try:
            raw_desc = str(row[raw_col]).strip()
            std_merch = str(row[std_col]).strip()
            
            if not raw_desc or not std_merch:
                errors.append({'row': idx, 'raw_description': raw_desc, 'reason': 'Empty fields'})
                skips += 1
                continue
            
            existing = db.query(MerchantMap).filter(
                MerchantMap.raw_description == raw_desc
            ).first()
            
            if existing:
                if replace_existing:
                    existing.standardized_merchant = std_merch
                    existing.updated_at = datetime.now()
                    updates += 1
                else:
                    skips += 1
            else:
                new_map = MerchantMap(
                    raw_description=raw_desc,
                    standardized_merchant=std_merch,
                    created_at=datetime.now()
                )
                db.session.add(new_map)
                inserts += 1
        
        except Exception as e:
            errors.append({'row': idx, 'raw_description': str(row[raw_col]), 'reason': str(e)})
    
    if not dry_run:
        db.session.commit()
    
    return {
        'success': True,
        'total_rows': len(df),
        'inserted': inserts,
        'updated': updates,
        'skipped': skips,
        'errors': errors,
        'preview': df.head(10) if dry_run else None
    }
```

#### Function 2: Import Category Map CSV

```python
def import_category_map_csv(
    file_path: str,
    user_id: int,
    replace_existing: bool = False,
    dry_run: bool = False
) -> dict:
    """
    Import category mapping CSV into category_map table.
    
    Expected CSV Columns:
    - unmapped_description (or 'Description', 'Raw_Description')
    - scsc_id (or 'SCSC_ID', 'ID')
    
    Validates:
    - All SCSC_IDs exist in category table
    - No duplicate unmapped_descriptions
    
    Returns: Same structure as import_merchant_map_csv
    """
    
    df = pd.read_csv(file_path)
    
    # Detect columns
    cols_lower = {c.lower(): c for c in df.columns}
    unmapped_col = cols_lower.get('unmapped_description') or cols_lower.get('description')
    scsc_col = cols_lower.get('scsc_id') or cols_lower.get('id')
    
    if not unmapped_col or not scsc_col:
        raise ValueError("CSV must contain 'unmapped_description' and 'scsc_id' columns")
    
    # Pre-load valid SCSC_IDs
    valid_scsc_ids = set(db.query(Category.id).all())
    
    errors = []
    inserts = 0
    updates = 0
    skips = 0
    
    for idx, row in df.iterrows():
        try:
            unmapped_desc = str(row[unmapped_col]).strip()
            scsc_id = str(row[scsc_col]).strip()
            
            if not unmapped_desc or not scsc_id:
                errors.append({'row': idx, 'unmapped_description': unmapped_desc, 'reason': 'Empty fields'})
                skips += 1
                continue
            
            if scsc_id not in valid_scsc_ids:
                errors.append({'row': idx, 'unmapped_description': unmapped_desc, 'reason': f'Invalid SCSC_ID: {scsc_id}'})
                skips += 1
                continue
            
            existing = db.query(CategoryMap).filter(
                CategoryMap.unmapped_description == unmapped_desc
            ).first()
            
            if existing:
                if replace_existing:
                    existing.scsc_id = scsc_id
                    existing.updated_at = datetime.now()
                    updates += 1
                else:
                    skips += 1
            else:
                new_map = CategoryMap(
                    unmapped_description=unmapped_desc,
                    scsc_id=scsc_id,
                    source='import',
                    created_at=datetime.now()
                )
                db.session.add(new_map)
                inserts += 1
        
        except Exception as e:
            errors.append({'row': idx, 'unmapped_description': str(row[unmapped_col]), 'reason': str(e)})
    
    if not dry_run:
        db.session.commit()
    
    return {
        'success': True,
        'total_rows': len(df),
        'inserted': inserts,
        'updated': updates,
        'skipped': skips,
        'errors': errors,
        'preview': df.head(10) if dry_run else None
    }
```

---

## Part 5: Analytics Functions for Merchant Intelligence

### Analytics Service: `services/merchant_analytics.py`

#### Function 1: Get Top Merchants by Volume

```python
def get_top_merchants(
    start_date: date,
    end_date: date,
    limit: int = 10,
    sort_by: str = 'amount'  # 'amount' or 'count'
) -> List[Dict]:
    """
    Get top merchants by spending volume or transaction count.
    
    Returns list of dicts with:
    {
        'standardized_merchant': str,
        'total_amount': float,
        'transaction_count': int,
        'avg_transaction': float,
        'section': str (optional),
        'category': str (optional),
        'subcategory': str (optional),
        'scsc_id': str (optional)
    }
    
    SQL Query (conceptual):
    SELECT 
        standardized_merchant,
        SUM(ABS(amount)) as total_amount,
        COUNT(*) as count,
        AVG(ABS(amount)) as avg_amount,
        section, category, subcategory, scsc_id
    FROM transaction
    LEFT JOIN category ON transaction.scsc_id = category.id
    WHERE date BETWEEN start_date AND end_date
        AND is_excluded = False
        AND amount < 0  -- Expenses only
    GROUP BY standardized_merchant
    ORDER BY {sort_by} DESC
    LIMIT {limit}
    """
    
    query = db.query(
        Transaction.standardized_merchant,
        func.sum(func.abs(Transaction.amount)).label('total_amount'),
        func.count(Transaction.id).label('transaction_count'),
        func.avg(func.abs(Transaction.amount)).label('avg_transaction'),
        Category.section,
        Category.category,
        Category.subcategory,
        Category.id.label('scsc_id')
    ).join(
        Category,
        Transaction.scsc_id == Category.id,
        isouter=True
    ).filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.is_excluded == False,
        Transaction.amount < 0  # Expenses
    ).group_by(
        Transaction.standardized_merchant
    )
    
    if sort_by == 'count':
        query = query.order_by(func.count(Transaction.id).desc())
    else:
        query = query.order_by(func.sum(func.abs(Transaction.amount)).desc())
    
    results = query.limit(limit).all()
    
    return [
        {
            'standardized_merchant': r[0],
            'total_amount': float(r[1] or 0),
            'transaction_count': int(r[2] or 0),
            'avg_transaction': float(r[3] or 0),
            'section': r[4],
            'category': r[5],
            'subcategory': r[6],
            'scsc_id': r[7]
        }
        for r in results
    ]
```

#### Function 2: Get Merchant Time Series

```python
def get_merchant_time_series(
    standardized_merchant: str,
    start_date: date,
    end_date: date,
    group_by: str = 'day'  # 'day', 'week', 'month'
) -> List[Dict]:
    """
    Get spending trend for a specific merchant over time.
    
    Returns:
    [
        {
            'date': date,
            'amount': float,
            'count': int,
            'avg_transaction': float
        },
        ...
    ]
    
    Useful for line charts showing spending trend.
    """
    
    # Group by logic
    if group_by == 'day':
        date_trunc = func.date(Transaction.date)
    elif group_by == 'week':
        date_trunc = func.strftime('%Y-%W', Transaction.date)  # Year-Week
    elif group_by == 'month':
        date_trunc = func.strftime('%Y-%m', Transaction.date)  # Year-Month
    else:
        date_trunc = func.date(Transaction.date)
    
    query = db.query(
        date_trunc.label('period'),
        func.sum(func.abs(Transaction.amount)).label('total_amount'),
        func.count(Transaction.id).label('count'),
        func.avg(func.abs(Transaction.amount)).label('avg_transaction')
    ).filter(
        Transaction.standardized_merchant == standardized_merchant,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.is_excluded == False,
        Transaction.amount < 0
    ).group_by(
        date_trunc
    ).order_by(
        date_trunc
    )
    
    results = query.all()
    
    return [
        {
            'date': r[0],
            'amount': float(r[1] or 0),
            'count': int(r[2] or 0),
            'avg_transaction': float(r[3] or 0)
        }
        for r in results
    ]
```

#### Function 3: Get Merchant Transactions (Drill-down)

```python
def get_merchant_transactions(
    standardized_merchant: str,
    start_date: date,
    end_date: date,
    limit: int = 50
) -> List[Dict]:
    """
    Get all transactions for a specific merchant.
    
    Returns:
    [
        {
            'id': int,
            'date': date,
            'raw_description': str,
            'standardized_merchant': str,
            'amount': float,
            'section': str,
            'category': str,
            'subcategory': str,
            'source': str
        },
        ...
    ]
    
    Used for transaction-level drill-down in UI.
    """
    
    query = db.query(
        Transaction.id,
        Transaction.date,
        Transaction.raw_description,
        Transaction.standardized_merchant,
        Transaction.amount,
        Category.section,
        Category.category,
        Category.subcategory,
        Transaction.source
    ).join(
        Category,
        Transaction.scsc_id == Category.id,
        isouter=True
    ).filter(
        Transaction.standardized_merchant == standardized_merchant,
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.is_excluded == False
    ).order_by(
        Transaction.date.desc()
    ).limit(limit)
    
    results = query.all()
    
    return [
        {
            'id': r[0],
            'date': r[1],
            'raw_description': r[2],
            'standardized_merchant': r[3],
            'amount': float(r[4]),
            'section': r[5],
            'category': r[6],
            'subcategory': r[7],
            'source': r[8]
        }
        for r in results
    ]
```

#### Function 4: Get Category-Based Aggregation

```python
def get_spending_by_category(
    start_date: date,
    end_date: date,
    group_level: str = 'category'  # 'section', 'category', or 'subcategory'
) -> List[Dict]:
    """
    Aggregate spending by section/category/subcategory.
    
    Useful for showing which categories are the biggest spenders.
    
    Returns:
    [
        {
            'section': str,
            'category': str,
            'subcategory': str (optional),
            'total_amount': float,
            'transaction_count': int,
            'merchants': List[str]  # Top merchants in this category
        },
        ...
    ]
    """
    
    if group_level == 'section':
        group_cols = [Category.section]
        group_labels = ('section',)
    elif group_level == 'category':
        group_cols = [Category.section, Category.category]
        group_labels = ('section', 'category')
    else:  # subcategory
        group_cols = [Category.section, Category.category, Category.subcategory]
        group_labels = ('section', 'category', 'subcategory')
    
    query = db.query(
        *group_cols,
        func.sum(func.abs(Transaction.amount)).label('total_amount'),
        func.count(Transaction.id).label('count')
    ).join(
        Category,
        Transaction.scsc_id == Category.id,
        isouter=True
    ).filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.is_excluded == False,
        Transaction.amount < 0
    ).group_by(
        *group_cols
    ).order_by(
        func.sum(func.abs(Transaction.amount)).desc()
    )
    
    results = query.all()
    
    return [
        {
            group_labels[i]: result[i] for i in range(len(group_labels))
        } | {
            'total_amount': float(result[-2] or 0),
            'transaction_count': int(result[-1] or 0)
        }
        for result in results
    ]
```

---

## Part 6: UI Components & Views

### Page: `ui/pages/merchant_intelligence.py`

#### Layout Structure

```
[Header: 🔍 Merchant Intelligence & Deep Dive]

[Controls Bar]
├─ Date Range Picker (Start Date → End Date)
├─ View Mode: [Top Merchants] [By Category] [By Section]
├─ Sort By: [Spending] [Frequency]
└─ Export: [Download CSV]

[Tabs]
├─ Tab 1: Top Merchants (List + Charts)
├─ Tab 2: Category Breakdown (Hierarchical)
└─ Tab 3: Merchant Deep Dive (Modal/Detail)

[Tab 1: Top Merchants]
┌──────────────────────────────────────────────────┐
│ Top 10 Merchants by Spending (YTD)               │
├──────────────────────────────────────────────────┤
│ Merchant Name    │ Amount  │ # Txns │ Category   │
├──────────────────────────────────────────────────┤
│ 1. Whole Foods   │ $1,250  │ 32     │ Groceries  │ ← Click to drill-down
│ 2. Safeway       │ $890    │ 18     │ Groceries  │
│ 3. Shell Gas     │ $750    │ 12     │ Gas        │
│ 4. McDonald's    │ $450    │ 25     │ Fast Food  │
│ ...              │ ...     │ ...    │ ...        │
└──────────────────────────────────────────────────┘

[Charts]
├─ Horizontal Bar Chart (Top 10 Merchants by Amount)
├─ Pie Chart (Spending Distribution by Top 10)
└─ Line Chart (Top 3 Merchants Trend Over Time)

[Tab 2: Category Breakdown]
┌──────────────────────────────────────────────────┐
│ Spending by Section                              │
├──────────────────────────────────────────────────┤
│ ▼ Housing ($2,800)                               │
│   ├─ Rent ($2,000)                               │
│   │  └─ Landlord Direct: $2,000                  │
│   └─ Utilities ($800)                            │
│      ├─ PG&E: $400                               │
│      └─ Comcast: $400                            │
│ ▼ Food & Dining ($2,590)                         │
│   ├─ Groceries ($1,250)                          │
│   │  ├─ Whole Foods: $600                        │
│   │  ├─ Safeway: $450                            │
│   │  └─ Trader Joe's: $200                       │
│   └─ Dining Out ($1,340)                         │
│      ├─ McDonald's: $450                         │
│      ├─ Starbucks: $380                          │
│      └─ ...                                      │
│ ▼ Transportation ($750)                          │
│   └─ Gas ($750)                                  │
│      ├─ Shell Gas: $400                          │
│      └─ Chevron: $350                            │
└──────────────────────────────────────────────────┘

[Tab 3: Merchant Deep Dive Modal]
When user clicks on a merchant:
┌────────────────────────────────────────────────────┐
│ 🔍 Whole Foods - Deep Dive                          │
├────────────────────────────────────────────────────┤
│ Standardized Name: Whole Foods                      │
│ Category: Food & Dining > Groceries > Supermarket   │
│ Period: Jan 1 - Dec 31, 2025                        │
├────────────────────────────────────────────────────┤
│ Metrics:                                            │
│  • Total Spent: $1,250.00                           │
│  • # Transactions: 32                               │
│  • Avg Transaction: $39.06                          │
│  • Min: $15.30 | Max: $125.50                       │
├────────────────────────────────────────────────────┤
│ [Chart 1: Trend Over Time (Line)]                   │
│  Spending by Month                                  │
│  ┌─────────────────────────────────────────────┐   │
│  │                                       Jan   │   │
│  │                           Dec             /  │   │
│  │                   Nov               /        │   │
│  │           Oct         /                      │   │
│  │   Sep                                        │   │
│  └─────────────────────────────────────────────┘   │
├────────────────────────────────────────────────────┤
│ [Chart 2: Distribution by Day of Week (Bar)]        │
│  Monday: 6 txns, Tuesday: 5 txns, ...              │
├────────────────────────────────────────────────────┤
│ Recent Transactions:                                │
│ ┌──────────┬────────────────┬──────────┬──────────┐ │
│ │ Date     │ Description    │ Amount   │ Source   │ │
│ ├──────────┼────────────────┼──────────┼──────────┤ │
│ │ 2025-01-18│ WHOLE FOODS #5621│ -$45.30│ Chase   │ │
│ │ 2025-01-15│ WHOLE FOODS #2341│ -$67.89│ Discover│ │
│ │ 2025-01-12│ WHOLE FOODS #1234│ -$52.15│ Chase   │ │
│ │ ...       │ ...            │ ...     │ ...     │ │
│ └──────────┴────────────────┴──────────┴──────────┘ │
│ [Load More] [Export Transactions]                  │
└────────────────────────────────────────────────────┘
```

---

### Component 1: Top Merchants List with Drill-down

```python
# ui/components/top_merchants_list.py

def render_top_merchants_list(start_date, end_date, limit=10):
    """
    Render interactive list of top merchants.
    Each row is clickable to open deep-dive modal.
    """
    
    merchants = get_top_merchants(start_date, end_date, limit=limit)
    
    # Create DataFrame for UI
    df_display = pd.DataFrame([
        {
            'Merchant': m['standardized_merchant'],
            'Total Spent': f"${m['total_amount']:.2f}",
            'Transactions': m['transaction_count'],
            'Avg': f"${m['avg_transaction']:.2f}",
            'Category': m['category'] or 'Uncategorized',
            'Section': m['section'] or '-'
        }
        for m in merchants
    ])
    
    # Display in ag-grid or table
    selected = ui.aggrid(
        df_display,
        columns_definition=[...],
        on_select=lambda row: show_merchant_deep_dive(row['Merchant'])
    )
    
    return selected
```

---

### Component 2: Merchant Deep Dive Modal

```python
# ui/components/merchant_deep_dive.py

def show_merchant_deep_dive(standardized_merchant, start_date, end_date):
    """
    Display comprehensive view of a single merchant.
    """
    
    # Get merchant data
    txns = get_merchant_transactions(standardized_merchant, start_date, end_date)
    time_series = get_merchant_time_series(standardized_merchant, start_date, end_date, group_by='month')
    
    # Calculate metrics
    total_spent = sum(abs(t['amount']) for t in txns)
    count = len(txns)
    avg = total_spent / count if count > 0 else 0
    min_amt = min(abs(t['amount']) for t in txns) if txns else 0
    max_amt = max(abs(t['amount']) for t in txns) if txns else 0
    
    # Get category info
    category_info = txns[0] if txns else None
    section = category_info['section'] if category_info else 'Uncategorized'
    category = category_info['category'] if category_info else '-'
    subcategory = category_info['subcategory'] if category_info else '-'
    
    with ui.dialog() as dialog:
        ui.label(f"🔍 {standardized_merchant} - Deep Dive").classes('text-2xl font-bold')
        
        # Metadata
        ui.label(f"Category: {section} > {category} > {subcategory}")
        ui.label(f"Period: {start_date.strftime('%b %d, %Y')} - {end_date.strftime('%b %d, %Y')}")
        
        # Metrics
        cols = ui.row()
        with cols:
            ui.metric('Total Spent', f"${total_spent:.2f}")
            ui.metric('# Transactions', count)
            ui.metric('Avg Transaction', f"${avg:.2f}")
            ui.metric('Min', f"${min_amt:.2f}")
            ui.metric('Max', f"${max_amt:.2f}")
        
        # Chart 1: Trend over time
        if time_series:
            fig = go.Figure()
            dates = [t['date'] for t in time_series]
            amounts = [t['amount'] for t in time_series]
            
            fig.add_trace(go.Scatter(
                x=dates,
                y=amounts,
                mode='lines+markers',
                name='Spending',
                line=dict(color='#1f77b4')
            ))
            
            fig.update_layout(
                title=f"{standardized_merchant} - Spending Trend",
                xaxis_title="Month",
                yaxis_title="Amount ($)"
            )
            
            ui.plotly(fig).classes('w-full')
        
        # Chart 2: Day-of-week distribution
        dow_dist = defaultdict(int)
        for t in txns:
            dow = t['date'].strftime('%A')
            dow_dist[dow] += 1
        
        if dow_dist:
            fig_dow = go.Figure()
            fig_dow.add_trace(go.Bar(
                x=list(dow_dist.keys()),
                y=list(dow_dist.values()),
                marker_color='#2ca02c'
            ))
            fig_dow.update_layout(
                title="Transactions by Day of Week",
                xaxis_title="Day",
                yaxis_title="# Transactions"
            )
            ui.plotly(fig_dow).classes('w-full')
        
        # Recent transactions table
        ui.label("Recent Transactions").classes('text-lg font-bold')
        df_txns = pd.DataFrame([
            {
                'Date': t['date'].strftime('%Y-%m-%d'),
                'Description': t['raw_description'][:30],
                'Amount': f"${abs(t['amount']):.2f}",
                'Source': t['source']
            }
            for t in txns[:20]
        ])
        
        ui.aggrid(
            df_txns,
            columns_definition=[...],
            rows_per_page=10
        )
        
        # Action buttons
        with ui.row():
            ui.button('Export Transactions', on_click=lambda: export_transactions_csv(txns))
            ui.button('Close', on_click=dialog.close).props('color=secondary')
    
    dialog.open()
```

---

### Component 3: Category Breakdown (Hierarchical Tree)

```python
# ui/components/category_breakdown.py

def render_category_breakdown(start_date, end_date):
    """
    Display spending by category in hierarchical structure.
    """
    
    # Get spending by section
    by_section = get_spending_by_category(start_date, end_date, group_level='section')
    
    for section_data in by_section:
        section_name = section_data['section']
        section_total = section_data['total_amount']
        
        with ui.expansion(f"▼ {section_name} (${section_total:.2f})"):
            # Get categories within section
            by_category = get_spending_by_category_in_section(section_name, start_date, end_date)
            
            for cat_data in by_category:
                cat_name = cat_data['category']
                cat_total = cat_data['total_amount']
                
                with ui.expansion(f"  ├─ {cat_name} (${cat_total:.2f})"):
                    # Get merchants in category
                    merchants = get_merchants_in_category(section_name, cat_name, start_date, end_date)
                    
                    for merch in merchants:
                        ui.label(f"    ├─ {merch['standardized_merchant']}: ${merch['total_amount']:.2f}")
```

---

## Part 7: CSV Import UI & Workflow

### UI Page: `ui/pages/import_mappings.py`

```
[Header: 📤 Import Mapping Files]

[Tabs]
├─ Tab 1: Merchant Mapping
├─ Tab 2: Category Mapping
└─ Tab 3: Upload History

[Tab 1: Merchant Mapping Import]
┌──────────────────────────────────────────────────┐
│ Current Status:                                  │
│  • Entries in Database: 245                      │
│  • Last Updated: 2025-01-10 10:30 AM             │
├──────────────────────────────────────────────────┤
│ Upload merchant_map.csv:                         │
│ [Drag & drop or click to upload]                 │
│                                                  │
│ Expected Columns:                                │
│  - raw_description (or 'Description')            │
│  - standardized_merchant (or 'Merchant')         │
├──────────────────────────────────────────────────┤
│ ☑ Replace existing entries (or skip duplicates)  │
│ ☑ Dry run (preview without committing)           │
├──────────────────────────────────────────────────┤
│ [Import] [Cancel]                                │
├──────────────────────────────────────────────────┤
│ Preview (if dry run):                            │
│ ┌──────────────────────────────────────────────┐ │
│ │ Would insert: 50 rows                        │ │
│ │ Would update: 15 rows                        │ │
│ │ Would skip: 5 rows (duplicates)              │ │
│ │ Errors: 2                                    │ │
│ │  • Row 12: Invalid merchant name              │ │
│ │  • Row 45: Empty field                        │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘

[Tab 2: Category Mapping Import]
[Similar to above, but for category_map.csv]
Current Status:
 • Entries in Database: 189
 • Last Updated: 2025-01-09 3:15 PM

Expected Columns:
 - unmapped_description (or 'Description')
 - scsc_id (or 'SCSC_ID')

Validation:
 • All SCSC_IDs must exist in Category table
 • No duplicate unmapped_descriptions

[Tab 3: Upload History]
┌──────────────────────────────────────────────────┐
│ Recent Imports                                   │
├──────────────────────────────────────────────────┤
│ Date       │ Type     │ Inserted │ Updated │ By   │
├──────────────────────────────────────────────────┤
│ 2025-01-10 │ Merchant │ 50       │ 15      │ User │
│ 2025-01-09 │ Category │ 30       │ 8       │ AI   │
│ 2025-01-08 │ Merchant │ 25       │ 5       │ User │
└──────────────────────────────────────────────────┘
[Show Details] [Revert] [Export] (for each row)
```

---

## Part 8: Export & Download Functionality

### Export Function 1: Export Merchant Map

```python
def export_merchant_map(file_format: str = 'csv'):
    """
    Export entire merchant_map table.
    
    Formats: 'csv', 'json'
    """
    
    records = db.query(MerchantMap).filter(MerchantMap.is_active == True).all()
    
    if file_format == 'csv':
        df = pd.DataFrame([
            {
                'raw_description': r.raw_description,
                'standardized_merchant': r.standardized_merchant,
                'updated_at': r.updated_at.isoformat()
            }
            for r in records
        ])
        
        return df.to_csv(index=False)
    
    elif file_format == 'json':
        data = {r.raw_description: r.standardized_merchant for r in records}
        return json.dumps(data, indent=2)
```

### Export Function 2: Export Category Map

```python
def export_category_map(file_format: str = 'csv'):
    """
    Export entire category_map table with category details.
    """
    
    records = db.query(CategoryMap).join(
        Category, CategoryMap.scsc_id == Category.id
    ).filter(CategoryMap.is_active == True).all()
    
    if file_format == 'csv':
        df = pd.DataFrame([
            {
                'unmapped_description': r.unmapped_description,
                'scsc_id': r.scsc_id,
                'section': r.category.section,
                'category': r.category.category,
                'subcategory': r.category.subcategory,
                'updated_at': r.updated_at.isoformat()
            }
            for r in records
        ])
        
        return df.to_csv(index=False)
    
    elif file_format == 'json':
        data = {r.unmapped_description: r.scsc_id for r in records}
        return json.dumps(data, indent=2)
```

### Export Function 3: Export Merchant Deep Dive Report

```python
def export_merchant_report(
    standardized_merchant: str,
    start_date: date,
    end_date: date
):
    """
    Export comprehensive merchant analysis as CSV or Excel.
    """
    
    txns = get_merchant_transactions(standardized_merchant, start_date, end_date, limit=None)
    
    df = pd.DataFrame([
        {
            'date': t['date'],
            'raw_description': t['raw_description'],
            'standardized_merchant': t['standardized_merchant'],
            'amount': t['amount'],
            'section': t['section'],
            'category': t['category'],
            'subcategory': t['subcategory'],
            'source': t['source']
        }
        for t in txns
    ])
    
    return df.to_csv(index=False)
```

---

## Part 9: Performance Considerations

### Database Indexing Strategy

```sql
-- For fast lookups in merchant enrichment
CREATE INDEX idx_merchant_raw_desc ON merchant_map(raw_description);
CREATE INDEX idx_merchant_std_name ON merchant_map(standardized_merchant);

-- For fast lookups in category enrichment
CREATE INDEX idx_category_unmapped ON category_map(unmapped_description);
CREATE INDEX idx_category_scsc_id ON category_map(scsc_id);

-- For analytics queries
CREATE INDEX idx_txn_date ON transaction(date);
CREATE INDEX idx_txn_merchant ON transaction(standardized_merchant);
CREATE INDEX idx_txn_scsc_id ON transaction(scsc_id);
CREATE INDEX idx_txn_excluded ON transaction(is_excluded);

-- For range queries
CREATE INDEX idx_txn_date_merchant ON transaction(date, standardized_merchant);
CREATE INDEX idx_txn_date_scsc ON transaction(date, scsc_id);
```

### Query Optimization

1. **Pre-load Maps in Memory:**
   - For bulk import/enrichment, load merchant_map and category_map into dictionaries
   - Avoid N+1 queries in enrichment loop

2. **Batch Processing:**
   - Import transactions in batches of 1000
   - Commit every batch to avoid lock timeout

3. **Materialized Views (Optional):**
   - Create pre-computed aggregations for daily reports
   - Refresh nightly

---

## Part 10: Migration Strategy from V1 CSVs to V2 Database

### Step 1: Initialize Database with Existing CSVs

```python
# services/migration_service.py

def migrate_v1_to_v2(
    merchant_map_csv_path: str,
    category_map_csv_path: str,
    category_taxonomy_csv_path: str
):
    """
    One-time migration from V1 CSV files to V2 database.
    """
    
    # Step 1: Import Category Taxonomy (foundation)
    print("1. Importing Category Taxonomy...")
    import_category_taxonomy(category_taxonomy_csv_path)
    
    # Step 2: Import Merchant Mappings
    print("2. Importing Merchant Mappings...")
    import_merchant_map_csv(merchant_map_csv_path, user_id=1)
    
    # Step 3: Import Category Mappings
    print("3. Importing Category Mappings...")
    import_category_map_csv(category_map_csv_path, user_id=1)
    
    print("✓ Migration complete!")
```

### Step 2: Enrich Existing Transactions

```python
# After importing maps, enrich all transactions

def migrate_transaction_enrichment():
    """
    Enrich all transactions with merchant and category mapping.
    """
    
    # Batch process in chunks
    batch_size = 1000
    total = db.query(func.count(Transaction.id)).scalar()
    
    for offset in range(0, total, batch_size):
        txns = db.query(Transaction).offset(offset).limit(batch_size).all()
        
        for txn in txns:
            txn = enrich_transaction(txn)
        
        db.session.commit()
        print(f"Enriched {offset + len(txns)} / {total}")
```

---

## Part 11: Data Validation & Integrity

### Validation Rules

1. **Merchant Map:**
   - raw_description: non-empty, unique
   - standardized_merchant: non-empty

2. **Category Map:**
   - unmapped_description: non-empty, unique
   - scsc_id: must exist in category table

3. **Transaction Enrichment:**
   - clean_description: auto-generated from raw_description
   - standardized_merchant: optional (fallback to clean_description)
   - scsc_id: optional (Uncategorized if unmapped)

### Error Handling

- **Duplicate Raw Description:** Log warning, skip or replace based on flag
- **Invalid SCSC_ID:** Log error, mark transaction as Uncategorized
- **Orphaned Mapping:** Alert user, allow manual update

---

## Part 12: Future Enhancements

1. **AI-Assisted Mapping:**
   - When a transaction is uncategorized, prompt user to accept AI suggestion
   - Save accepted mappings automatically

2. **Merchant Alias Management:**
   - Allow users to define multiple standardized names for same merchant
   - Merge merchants if duplicates detected

3. **Spending Alerts:**
   - Alert if spending on merchant X exceeds threshold in month Y
   - Predictive: "You'll exceed budget for Groceries by EOMonth"

4. **Merchant Seasonality:**
   - Track seasonal patterns (e.g., higher spending in Dec for retail)
   - Adjust budget recommendations based on historical patterns

---

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Create MerchantMap table
- [ ] Create CategoryMap table (enhance from Step 1)
- [ ] Update Transaction table with enrichment fields
- [ ] Write migration script from CSV to DB

### Phase 2: Enrichment Pipeline
- [ ] Write enrichment_service.py with enrich_transaction()
- [ ] Write merchant_analytics.py with all query functions
- [ ] Implement batch enrichment for imports

### Phase 3: CSV Import UI
- [ ] Build import_mappings.py page
- [ ] Create CSV upload components
- [ ] Implement dry-run preview
- [ ] Add upload history tracking

### Phase 4: Merchant Intelligence UI
- [ ] Build merchant_intelligence.py page
- [ ] Create top_merchants_list component
- [ ] Create merchant_deep_dive modal
- [ ] Create category_breakdown hierarchical tree

### Phase 5: Export & Analytics
- [ ] Implement export functions (CSV, JSON)
- [ ] Add merchant drill-down charts (line, bar, pie)
- [ ] Add time-series visualizations
- [ ] Add transaction-level export

### Phase 6: Performance & Optimization
- [ ] Add database indexes
- [ ] Implement batch processing
- [ ] Test with 10K+ transactions
- [ ] Optimize slow queries

---

## Summary: Data Flow from CSV to UI

```
V1: CSV Files
├─ merchant_map.csv
├─ ChatGPT_normalization_map_ID.csv
└─ Sections_category_subcategory.csv
        ↓
        ↓ [Bulk Import]
        ↓
V2: Database Tables
├─ merchant_map
├─ category_map
└─ category
        ↓
        ↓ [Enrichment Service]
        ↓
Transaction Enrichment
├─ standardized_merchant (via merchant_map)
├─ scsc_id (via category_map)
└─ section, category, subcategory (via category)
        ↓
        ↓ [Analytics Service]
        ↓
Query Results
├─ get_top_merchants()
├─ get_merchant_time_series()
├─ get_spending_by_category()
└─ get_merchant_transactions()
        ↓
        ↓ [Charts & Visualization]
        ↓
UI Components
├─ Top Merchants List
├─ Merchant Deep Dive Modal
├─ Category Breakdown Tree
├─ Spending Trend Charts
└─ Transaction Drill-down Table
```

---

## Key Takeaways

1. **Centralized Data Model:** All merchant and category mappings are now in the database, not CSVs. This enables real-time updates and querying.

2. **Transaction Enrichment:** Every transaction is enriched with standardized merchant name and SCSC_ID at import time, enabling instant analytics.

3. **CSV Bulk Import:** Users can still import CSVs to update merchant_map and category_map tables, maintaining flexibility.

4. **Hierarchical Analytics:** Spending can be viewed by merchant, category, subcategory, or section—all in one view.

5. **Drill-down Capability:** Click on any merchant or category to see time-series trends, transaction history, and detailed breakdowns.

6. **Performance:** Database indexes and batch processing ensure smooth performance even with large transaction volumes.

7. **Audit Trail:** timestamp and source fields track when mappings were created/updated and by whom, enabling rollback if needed.
