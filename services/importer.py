import pandas as pd
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from database.models import Transaction, Category, MerchantMap, CategoryMap, ExclusionRule
import re

def check_exclusion(description: str, rules: list) -> bool:
    """
    Checks if a description matches any exclusion rules.
    rules: list of ExclusionRule objects
    """
    if not description:
        return False
        
    for rule in rules:
        if not rule.is_active:
            continue
            
        if rule.rule_type == 'exact_match':
            if rule.value.lower() == description.lower():
                return True
        elif rule.rule_type == 'contains': # New support
            if rule.value.lower() in description.lower():
                return True
        elif rule.rule_type == 'regex':
            try:
                if re.search(rule.value, description, re.IGNORECASE):
                    return True
            except re.error:
                continue # Skip invalid regex
    return False

def apply_mapping_rules(tx: Transaction, db: Session):
    """
    Refactored helper: Applies Merchant Maps and Category Maps to a Transaction object.
    Does NOT commit.
    """
    # 1. Normalization (Merchant Map)
    # Match raw_description against MerchantMap
    # Note: MerchantMap stores exact raw descriptions. 
    # For robust matching, we might want "contains" logic in the database, 
    # but currently V1 logic is exact match on `raw_description` OR we do the cleaning here.
    
    # Let's try to find an exact match first on description
    m_map = db.query(MerchantMap).filter(MerchantMap.raw_description == tx.description).first()
    
    if m_map and m_map.is_active:
        tx.standardized_merchant = m_map.standardized_merchant
        tx.merchant_map_id = m_map.id
        tx.clean_description = m_map.standardized_merchant # Update display desc
    else:
        # Fallback: Just clean the string if no map
        # Simplified cleaning here or use AI service later
        tx.clean_description = tx.description 

    # 2. Categorization (Category Map)
    # Match description against CategoryMap 'unmapped_description'
    c_map = db.query(CategoryMap).filter(CategoryMap.unmapped_description == tx.description).first()
    
    # If not found by exact desc, try by standardized merchant
    if not c_map and tx.standardized_merchant:
        c_map = db.query(CategoryMap).filter(CategoryMap.unmapped_description == tx.standardized_merchant).first()

    if c_map and c_map.is_active:
        tx.category_id = c_map.scsc_id
        tx.category_map_id = c_map.id

def generate_fingerprint(date_dt: datetime, amount: float, description: str):
    """
    Generates a deterministic SHA256 hash for a transaction.
    Format: YYYY-MM-DD|AMOUNT|DESCRIPTION
    """
    date_str = date_dt.strftime("%Y-%m-%d")
    # Clean description: remove multiple spaces, strip
    desc_clean = " ".join(str(description).split()).strip()
    raw_str = f"{date_str}|{float(amount):.2f}|{desc_clean}"
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()

def normalize_bank_row(row, cols_map):
    """
    Takes a dataframe row and the column map, returns a standardized dict:
    {
        'date': datetime,
        'amount': float,
        'description': str,
        'raw_description': str,
        'type': str,
        'account_name': str (optional)
    }
    """
    # 1. DATE Parsing
    date_val = None
    # Priority: Transaction Date > Posting Date > Date
    for k in ['transaction date', 'posting date', 'post date', 'date']:
        raw_d = row.get(cols_map.get(k))
        if pd.notna(raw_d):
            try:
                # pandas handles most formats (MM/DD/YYYY, YYYY-MM-DD) automatically
                date_val = pd.to_datetime(raw_d).to_pydatetime()
                break
            except:
                continue
    
    if not date_val:
        return None

    # 4. TYPE Parsing (Moved up to support Amount logic)
    txn_type = ""
    for k in ['transaction type', 'type', 'details', 'd/c', 'dr/cr', 'sign']:
        val = row.get(cols_map.get(k))
        if pd.notna(val):
            txn_type = str(val).strip()
            break

    # 2. AMOUNT Parsing
    amount = 0.0
    amount_sign_fixed = False
    amount_parsed_successfully = False
    
    # Check for direct Amount column
    amt_col = cols_map.get('amount') or cols_map.get('transaction amount')
    if amt_col:
        val = row.get(amt_col)
        if pd.notna(val) and str(val).strip() != '':
            if isinstance(val, str):
                val = val.replace('$','').replace(',','').replace(' ','')
                # Handle parenthesis negations (100.00) -> -100.00
                if '(' in val and ')' in val:
                     val = '-' + val.replace('(','').replace(')','')
            try:
                amount = float(val)
                amount_parsed_successfully = True
            except:
                pass
    
    # Check for Split Debit/Credit columns (Common in BECU, Capital One)
    # Use if Amount col was missing OR it failed to parse/was empty
    if not amount_parsed_successfully and (cols_map.get('debit') or cols_map.get('credit')):
        debit_val = 0.0
        credit_val = 0.0
        
        # Parse Debit
        d_col = cols_map.get('debit')
        if d_col:
            val = row.get(d_col)
            if pd.notna(val) and str(val).strip() != '':
                if isinstance(val, str):
                    val = val.replace('$','').replace(',','')
                try:
                    debit_val = abs(float(val)) 
                except:
                    pass

        # Parse Credit
        c_col = cols_map.get('credit')
        if c_col:
            val = row.get(c_col)
            if pd.notna(val) and str(val).strip() != '':
                if isinstance(val, str):
                    val = val.replace('$','').replace(',','')
                try:
                    credit_val = abs(float(val))
                except:
                    pass
        
        # Only use this if we actually found something
        # Explicit check prevents overwriting if just one column exists but is empty
        if debit_val != 0 or credit_val != 0:
             amount = credit_val - debit_val
             amount_sign_fixed = True
        # Edge case: Both zero but columns exist - likely a $0.00 transaction or transfer
        elif pd.notna(row.get(d_col)) or pd.notna(row.get(c_col)):
            amount = credit_val - debit_val # 0.0
            amount_sign_fixed = True

    # SIGN CORRECTION using Type (if not already fixed by split cols)
    if not amount_sign_fixed and amount != 0:
        t_lower = txn_type.lower()
        if t_lower in ['debit', 'dr', 'withdrawal', 'outflow', 'sale', 'payment', 'fee']:
            amount = -abs(amount)
        elif t_lower in ['credit', 'cr', 'deposit', 'inflow', 'refund']:
            amount = abs(amount)

    # 3. DESCRIPTION Parsing
    # Priority: Description > Transaction Description > Merchant
    desc = ""
    for k in ['transaction description', 'description', 'merchant', 'narrative', 'memo']:
        val = row.get(cols_map.get(k))
        if pd.notna(val):
            desc = str(val).strip()
            break
            
    # 5. ACCOUNT NAME (Source)
    # Some CSVs might have 'Card No.' or 'Account Number'
    acc_name = "Imported CSV"
    for k in ['account name', 'card no.', 'card no', 'account number']:
        val = row.get(cols_map.get(k))
        # SimpleFin CSV uses 'Source' as Account Name
        s_val = row.get(cols_map.get('source'))
        
        if pd.notna(s_val):
            acc_name = str(s_val).strip()
            break
        elif pd.notna(val):
            acc_name = f"Account {val}"
            break

    return {
        'date': date_val,
        'amount': amount,
        'description': desc,
        'raw_description': desc, # Default raw to same as desc for CSVs
        'type': txn_type,
        'account_name': acc_name
    }


def import_transactions_from_df(db: Session, df: pd.DataFrame, source_label="csv"):
    """
    Imports transactions from a Pandas DataFrame, applying mappings and fingerprinting.
    Returns a dict with statistics.
    """
    # 1. Load Mappings
    merchant_rules = {m.raw_description: m.standardized_merchant for m in db.query(MerchantMap).all()}
    category_rules = {c.unmapped_description: c.scsc_id for c in db.query(CategoryMap).all()}
    exclusion_rules = db.query(ExclusionRule).filter(ExclusionRule.is_active == True).all()

    # Create a lower-case map of columns for loose matching
    cols_map = {c.lower().strip(): c for c in df.columns}
    
    # Track fingerprints seen in this specific batch to avoid duplicates within the CSV itself
    batch_fingerprints = set()

    stats = {
        'total_rows': len(df),
        'added': 0,
        'skipped': 0,
        'existing': 0,
        'errors': 0,
        'skipped_details': [],
        'error_details': []
    }

    for idx, row in df.iterrows():
        try:
            norm_data = normalize_bank_row(row, cols_map)
            
            if not norm_data:
                stats['skipped'] += 1
                stats['skipped_details'].append(f"Row {idx+2}: Could not parse date or required fields.")
                continue
            
            # --- Apply Mappings ---
            
            # 1. Merchant Map (Raw Description -> Standardized Merchant)
            # Use raw description from normalization
            raw_desc = norm_data['raw_description']
            std_merchant = merchant_rules.get(raw_desc)
            if not std_merchant:
                # Fallback: if no rule, default standardized merchant can be the clean description or empty
                std_merchant = None 

            # 2. Category Map (Description -> Category ID)
            # Logic: We often map based on the 'Unmapped Description' field in CSV which corresponds to 'raw_description' 
            # OR the cleaned description. The requirements say 'CategoryMap (Description -> SCSC_ID)'.
            # Let's try to match the exact raw description first, as that's usually most reliable for rules.
            cat_id = category_rules.get(raw_desc)
            
            # Generate Fingerprint
            fp = generate_fingerprint(norm_data['date'], norm_data['amount'], norm_data['description'])
            
            # Check for matches
            # 1. Check if we already processed this fingerprint in this batch (duplicate in CSV)
            if fp in batch_fingerprints:
                stats['skipped'] += 1
                stats['skipped_details'].append(f"Row {idx+2}: Duplicate within file (Fingerprint clash).")
                continue
            
            # Check Exclusion
            is_excluded = check_exclusion(norm_data['description'], exclusion_rules)

            # 2. Check existing DB fingerprints
            existing = db.query(Transaction).filter(Transaction.fingerprint == fp).first()
            if existing:
                # If existing, we could potentially update the exclusion status if rules changed?
                # For now, let's leave it. If user wants to re-apply rules, they can use the UI tool.
                stats['skipped'] += 1
                stats['existing'] += 1
                # We typically don't log every existing transaction as "error" but we can track count
                continue
                
            # Create Transaction
            new_tx = Transaction(
                fingerprint=fp,
                date=norm_data['date'],
                amount=norm_data['amount'],
                description=norm_data['description'],
                raw_description=raw_desc,
                clean_description=norm_data['description'], # Start with raw
                standardized_merchant=std_merchant,
                category_id=cat_id,
                type=norm_data['type'],
                account_name=norm_data['account_name'],
                import_method="csv",
                source_file=source_label,
                is_excluded=is_excluded
            )
            
            db.add(new_tx)
            batch_fingerprints.add(fp)
            stats['added'] += 1
            
        except Exception as e:
            stats['errors'] += 1
            stats['error_details'].append(f"Row {idx+2} Error: {str(e)}")
            continue

    try:
        db.commit()
    except Exception as e:
        stats['error_details'].append(f"Batch Commit Failed: {str(e)}")
        db.rollback()
        
    return stats


def import_csv_transactions(db: Session, csv_path: str, source_label="csv"):
    """
    Reads a Bank CSV, detects schema, handles variations (Debit/Credit vs Amount),
    and inserts into DB with SimpleFin-compatible fields.
    """
    try:
        # Read without header assumption first to inspect? No, assume standard header rows.
        df = pd.read_csv(csv_path)
        return import_transactions_from_df(db, df, source_label)
    except Exception as e:
        return {
            'total_rows': 0,
            'added': 0,
            'skipped': 0,
            'existing': 0,
            'errors': 1,
            'skipped_details': [],
            'error_details': [f"Critical CSV Error {csv_path}: {str(e)}"]
        }

def sync_simplefin_data_list(db: Session, transactions_json: list):
    """
    Syncs list of dicts from SimpleFin API (or simplefin_transactions.csv loaded as dicts).
    """
    added = 0
    merged = 0
    skipped = 0
    
    for item in transactions_json:
        # Map fields from SimpleFin Schema
        # Item keys might differ if via API or CSV. 
        # Assuming we adapt API response to this dict structure before calling this text.
        
        # Handle 'posted' -> date conversion
        if 'posted' in item and isinstance(item['posted'], int):
            dt = datetime.fromtimestamp(item['posted'])
        elif 'date' in item:
            # If standard string
            try:
                dt = pd.to_datetime(item['date']).to_pydatetime()
            except:
                continue
        else:
            continue

        amount = float(item.get('amount', 0))
        desc = item.get('description', '')
        sf_id = item.get('id')
        account = item.get('source') or item.get('org', {}).get('name')
        
        # 1. Idempotency by SimpleFin ID
        if sf_id:
            existing_sf = db.query(Transaction).filter(Transaction.simplefin_id == sf_id).first()
            if existing_sf:
                skipped += 1
                continue
                
        # 2. Merge check (Fingerprint)
        fp = generate_fingerprint(dt, amount, desc)
        existing_fp = db.query(Transaction).filter(Transaction.fingerprint == fp).first()
        
        if existing_fp:
            # Upgrade existing CSV row to Connected row
            if sf_id: existing_fp.simplefin_id = sf_id
            existing_fp.account_name = account # Update account name to official one
            existing_fp.import_method = "simplefin_merge"
            existing_fp.source_file = "SimpleFin" # Update source per user request
            if item.get('pending') is False:
                 pass # Could update status
            merged += 1
        else:
            new_tx = Transaction(
                simplefin_id=sf_id,
                fingerprint=fp,
                date=dt,
                amount=amount,
                description=desc,
                raw_description=desc,
                clean_description=desc,
                account_name=account,
                import_method="simplefin_api",
                source_file="SimpleFin",
                type=item.get('type', '')
            )
            db.add(new_tx)
            added += 1
            
    db.commit()
    return added, merged, skipped
