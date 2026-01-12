import pandas as pd
import os
import sys
import numpy as np

# Add parent directory to path to import database modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import SessionLocal, engine, Base
from database.models import Category, MerchantMap, CategoryMap, Budget, ExclusionRule

def clean_val(val):
    if pd.isna(val) or val == 'nan' or val == '':
        return None
    return str(val).strip()

def seed_exclusions(session, root_dir):
    # Support exclude.csv and exclude.txt
    files = ['exclude.csv', 'exclude.txt']
    
    for fname in files:
        fpath = os.path.join(root_dir, fname)
        if not os.path.exists(fpath):
            continue
            
        print(f"Seeding exclusions from {fname}...")
        try:
            # Check if CSV or simple text
            if fname.endswith('.csv'):
                try:
                    df = pd.read_csv(fpath, header=None)
                    # Assume single column or handle potential variations
                    # If multiple columns, we look for first string col
                    values = df.iloc[:,0].dropna().astype(str).tolist()
                except:
                    # Fallback to text read if CSV parse fails
                    with open(fpath, 'r') as f:
                        values = [line.strip() for line in f if line.strip()]
            else:
                 with open(fpath, 'r') as f:
                        values = [line.strip() for line in f if line.strip()]
            
            count = 0
            for val in values:
                # Basic cleanup
                val = val.strip()
                if not val: continue
                
                # Check for duplicate in DB
                existing = session.query(ExclusionRule).filter(ExclusionRule.value == val).first()
                if not existing:
                    # Determine regex vs exact match heuristically?
                    # Prompt says: "treat them as `rule_type='exact_match'` (or `regex` if they look like patterns)."
                    # Simple heuristic: if contains regex chars like ^, $, *, etc., assume regex.
                    # Otherwise default to exact match.
                    is_regex = any(c in val for c in ['^', '$', '.*', '[', '(', '|'])
                    rtype = 'regex' if is_regex else 'exact_match'
                    
                    rule = ExclusionRule(rule_type=rtype, value=val, is_active=True)
                    session.add(rule)
                    count += 1
            
            session.commit()
            print(f"  -> Added {count} exclusion rules.")
            
        except Exception as e:
            print(f"Error reading {fname}: {e}")

def seed():
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    
    session = SessionLocal()
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        # Seeding Exclusions First
        seed_exclusions(session, root_dir)

        # 1. Categories
        csv_path = os.path.join(root_dir, "Sections_category_subcategory.csv")
        if os.path.exists(csv_path):
            print(f"Seeding Categories from {csv_path}...")
            df = pd.read_csv(csv_path)
            # Expected cols: ID, Section, Category, Subcategory
            
            count = 0
            for _, row in df.iterrows():
                cid = clean_val(row['ID'])
                if not cid: continue
                
                section = clean_val(row['Section'])
                category = clean_val(row['Category'])
                subcategory = clean_val(row.get('Subcategory'))

                existing = session.query(Category).filter_by(id=cid).first()
                if not existing:
                    cat = Category(
                        id=cid,
                        section=section or "Unknown",
                        category=category or "Unknown",
                        subcategory=subcategory
                    )
                    session.add(cat)
                else:
                    existing.section = section or "Unknown"
                    existing.category = category or "Unknown"
                    existing.subcategory = subcategory
                count += 1
            session.commit()
            print(f"Processed {count} categories.")
        else:
            print(f"Skipping Categories: {csv_path} not found.")

        # 2. MerchantMap
        csv_path = os.path.join(root_dir, "merchant_map.csv")
        if os.path.exists(csv_path):
            print(f"Seeding Merchant Maps from {csv_path}...")
            df = pd.read_csv(csv_path)
            # Cols: Raw_Description, Standardized_Merchant
            
            count = 0
            for _, row in df.iterrows():
                raw = clean_val(row['Raw_Description'])
                std = clean_val(row['Standardized_Merchant'])
                
                if not raw or not std: continue

                existing = session.query(MerchantMap).filter_by(raw_description=raw).first()
                if not existing:
                    m = MerchantMap(raw_description=raw, standardized_merchant=std)
                    session.add(m)
                else:
                    existing.standardized_merchant = std
                count += 1
            session.commit()
            print(f"Processed {count} merchant maps.")
        else:
            print(f"Skipping MerchantMap: {csv_path} not found.")

        # 3. CategoryMap
        csv_path = os.path.join(root_dir, "ChatGPT_normalization_map_ID.csv")
        if os.path.exists(csv_path):
            print(f"Seeding Category Maps from {csv_path}...")
            df = pd.read_csv(csv_path)
            # Cols: Unmapped_Description, SCSC_ID
            
            count = 0
            for _, row in df.iterrows():
                desc = clean_val(row['Unmapped_Description'])
                scsc = clean_val(row['SCSC_ID'])
                
                if not desc or not scsc: continue

                existing = session.query(CategoryMap).filter_by(unmapped_description=desc).first()
                if not existing:
                    cm = CategoryMap(unmapped_description=desc, scsc_id=scsc)
                    session.add(cm)
                else:
                    existing.scsc_id = scsc
                count += 1
            session.commit()
            print(f"Processed {count} category maps.")
        else:
            print(f"Skipping CategoryMap: {csv_path} not found.")

        # 4. Budget
        csv_path = os.path.join(root_dir, "budget.csv")
        if os.path.exists(csv_path):
            print(f"Seeding Budget from {csv_path}...")
            df = pd.read_csv(csv_path)
            # Cols: SCSC_ID, Amount
            
            count = 0
            for _, row in df.iterrows():
                scsc = clean_val(row['SCSC_ID'])
                # Handle amount carefully, clear '$' or ','
                amt_raw = row['Amount']
                try:
                    if isinstance(amt_raw, str):
                        amt_raw = amt_raw.replace('$', '').replace(',', '')
                    amt = float(amt_raw)
                except:
                    amt = 0.0

                if not scsc: continue
                
                existing = session.query(Budget).filter_by(scsc_id=scsc).first()
                if not existing:
                    b = Budget(scsc_id=scsc, amount=amt)
                    session.add(b)
                else:
                    existing.amount = amt
                count += 1
            session.commit()
            print(f"Processed {count} budget items.")
        else:
            print(f"Skipping Budget: {csv_path} not found.")

        print("Seeding complete.")

    except Exception as e:
        print(f"Error seeding data: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    seed()
