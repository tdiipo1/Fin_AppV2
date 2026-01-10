import pandas as pd
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..database.models import Transaction, Category, MappingRule

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

    # 2. AMOUNT Parsing
    # Logic: 
    # - If 'Amount' exists, use it.
    # - If 'Debit' and 'Credit' exist, combine them.
    amount = 0.0
    
    # Check for direct Amount column
    amt_col = cols_map.get('amount') or cols_map.get('transaction amount')
    if amt_col and pd.notna(row.get(amt_col)):
        # Clean currency symbols if any (though pandas read_csv usually handles types, sometimes strings sneak in)
        val = row.get(amt_col)
        if isinstance(val, str):
            val = val.replace('$','').replace(',','')
        try:
            amount = float(val)
        except:
            amount = 0.0
    
    # Check for Split Debit/Credit columns (Common in BECU, Capital One)
    elif cols_map.get('debit') or cols_map.get('credit'):
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
                    debit_val = abs(float(val)) # Treat debit as abs magnitude
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
        
        # Calculate Net Amount (Income = Positive, Expense = Negative)
        # If Debit is present, it's an outflow (-)
        # If Credit is present, it's an inflow (+)
        amount = credit_val - debit_val

    # 3. DESCRIPTION Parsing
    # Priority: Description > Transaction Description > Merchant
    desc = ""
    for k in ['transaction description', 'description', 'merchant', 'narrative', 'memo']:
        val = row.get(cols_map.get(k))
        if pd.notna(val):
            desc = str(val).strip()
            break
            
    # 4. TYPE Parsing
    txn_type = ""
    for k in ['transaction type', 'type', 'details']:
        val = row.get(cols_map.get(k))
        if pd.notna(val):
            txn_type = str(val).strip()
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


def import_csv_transactions(db: Session, csv_path: str, source_label="csv"):
    """
    Reads a Bank CSV, detects schema, handles variations (Debit/Credit vs Amount),
    and inserts into DB with SimpleFin-compatible fields.
    """
    try:
        # Read without header assumption first to inspect? No, assume standard header rows.
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV {csv_path}: {e}")
        return 0, 0

    # Create a lower-case map of columns for loose matching
    cols_map = {c.lower().strip(): c for c in df.columns}
    
    added = 0
    skipped = 0

    for idx, row in df.iterrows():
        try:
            norm_data = normalize_bank_row(row, cols_map)
            if not norm_data:
                continue

            # Generate Fingerprint
            fp = generate_fingerprint(norm_data['date'], norm_data['amount'], norm_data['description'])
            
            # Check for matches
            # 1. Check existing CSV fingerprints
            existing = db.query(Transaction).filter(Transaction.fingerprint == fp).first()
            if existing:
                skipped += 1
                continue
                
            # Create Transaction
            new_tx = Transaction(
                fingerprint=fp,
                date=norm_data['date'],
                amount=norm_data['amount'],
                description=norm_data['description'],
                raw_description=norm_data['raw_description'],
                clean_description=norm_data['description'], # Start with raw
                type=norm_data['type'],
                account_name=norm_data['account_name'],
                import_method='csv'
            )
            
            db.add(new_tx)
            added += 1
            
        except Exception as e:
            print(f"Error importing row {idx}: {e}")
            continue

    try:
        db.commit()
    except Exception as e:
        print(f"Commit failed: {e}")
        db.rollback()
        
    return added, skipped

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
                type=item.get('type', '')
            )
            db.add(new_tx)
            added += 1
            
    db.commit()
    return added, merged, skipped
