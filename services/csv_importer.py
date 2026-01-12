import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from database.models import MerchantMap, CategoryMap, Category
import os

def import_merchant_map_csv(
    db: Session,
    file_path: str,
    replace_existing: bool = False,
    dry_run: bool = False
) -> dict:
    """
    Import merchant mapping CSV into merchant_map table.
    """
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        return {'success': False, 'error': str(e)}
    
    # Detect columns
    cols_lower = {c.lower().strip(): c for c in df.columns}
    raw_col = cols_lower.get('raw_description') or cols_lower.get('description')
    std_col = cols_lower.get('standardized_merchant') or cols_lower.get('merchant') or cols_lower.get('standardized_name')
    
    if not raw_col or not std_col:
        return {'success': False, 'error': "CSV must contain 'raw_description' and 'standardized_merchant' columns"}
    
    errors = []
    inserts = 0
    updates = 0
    skips = 0
    
    preview_rows = []

    for idx, row in df.iterrows():
        try:
            raw_desc = str(row[raw_col]).strip()
            std_merch = str(row[std_col]).strip()
            
            if not raw_desc or not std_merch or raw_desc.lower() == 'nan' or std_merch.lower() == 'nan':
                skips += 1
                continue
            
            # Check existing
            existing = db.query(MerchantMap).filter(MerchantMap.raw_description == raw_desc).first()
            
            action = "skip"
            if existing:
                if replace_existing:
                    action = "update"
                    updates += 1
                    if not dry_run:
                        existing.standardized_merchant = std_merch
                        existing.updated_at = datetime.utcnow()
                else:
                    skips += 1
            else:
                action = "insert"
                inserts += 1
                if not dry_run:
                    new_map = MerchantMap(
                        raw_description=raw_desc,
                        standardized_merchant=std_merch,
                        created_at=datetime.utcnow()
                    )
                    db.add(new_map)
            
            if dry_run:
                preview_rows.append({
                    'raw_description': raw_desc,
                    'standardized_merchant': std_merch,
                    'action': action
                })

        except Exception as e:
            errors.append({'row': idx, 'error': str(e)})
    
    if not dry_run:
        db.commit()
    
    return {
        'success': True,
        'total_rows': len(df),
        'inserted': inserts,
        'updated': updates,
        'skipped': skips,
        'errors': errors,
        'preview': preview_rows if dry_run else None
    }

def import_category_map_csv(
    db: Session,
    file_path: str,
    replace_existing: bool = False,
    dry_run: bool = False
) -> dict:
    """
    Import category mapping CSV into category_map table.
    """
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        return {'success': False, 'error': str(e)}
    
    # Detect columns
    cols_lower = {c.lower().strip(): c for c in df.columns}
    unmapped_col = cols_lower.get('unmapped_description') or cols_lower.get('description') or cols_lower.get('merchant')
    scsc_col = cols_lower.get('scsc_id') or cols_lower.get('id') or cols_lower.get('category_id')
    
    if not unmapped_col or not scsc_col:
        return {'success': False, 'error': "CSV must contain 'unmapped_description' and 'scsc_id' columns"}
    
    # Cache valid IDs
    valid_ids = {r[0] for r in db.query(Category.id).all()}
    
    errors = []
    inserts = 0
    updates = 0
    skips = 0
    preview_rows = []
    
    for idx, row in df.iterrows():
        try:
            desc = str(row[unmapped_col]).strip()
            cat_id = str(row[scsc_col]).strip()
            
            if not desc or not cat_id or desc.lower() == 'nan': 
                continue

            if cat_id not in valid_ids:
                errors.append({'row': idx, 'error': f"Invalid SCSC_ID: {cat_id}"})
                continue
                
            existing = db.query(CategoryMap).filter(CategoryMap.unmapped_description == desc).first()
            
            action = "skip"
            if existing:
                if replace_existing:
                    action = "update"
                    updates += 1
                    if not dry_run:
                        existing.scsc_id = cat_id
                        existing.updated_at = datetime.utcnow()
                else:
                    skips += 1
            else:
                action = "insert"
                inserts += 1
                if not dry_run:
                    new_map = CategoryMap(
                        unmapped_description=desc,
                        scsc_id=cat_id,
                        source='import',
                        created_at=datetime.utcnow()
                    )
                    db.add(new_map)

            if dry_run:
                preview_rows.append({'description': desc, 'scsc_id': cat_id, 'action': action})

        except Exception as e:
            errors.append({'row': idx, 'error': str(e)})

    if not dry_run:
        db.commit()

    return {
        'success': True,
        'total_rows': len(df),
        'inserted': inserts,
        'updated': updates,
        'skipped': skips,
        'errors': errors,
        'preview': preview_rows if dry_run else None
    }

def import_category_taxonomy_csv(
    db: Session,
    file_path: str,
    replace_existing: bool = False,
    dry_run: bool = False
) -> dict:
    """
    Import category taxonomy (Section > Category > Subcategory).
    Expected columns: ID, Section, Category, Subcategory
    """
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        return {'success': False, 'error': str(e)}
        
    cols_lower = {c.lower().strip(): c for c in df.columns}
    id_col = cols_lower.get('id') or cols_lower.get('scsc_id')
    sec_col = cols_lower.get('section')
    cat_col = cols_lower.get('category')
    sub_col = cols_lower.get('subcategory') # Optional/Nullable
    
    if not id_col or not sec_col or not cat_col:
        return {'success': False, 'error': "CSV must contain ID, Section, and Category columns"}
        
    errors = []
    inserts = 0
    updates = 0
    skips = 0
    preview_rows = []
    
    for idx, row in df.iterrows():
        try:
            cat_id = str(row[id_col]).strip()
            section = str(row[sec_col]).strip()
            category = str(row[cat_col]).strip()
            subcategory = str(row[sub_col]).strip() if sub_col and pd.notna(row[sub_col]) else None
            
            if not cat_id or not section or not category:
                continue
                
            existing = db.query(Category).filter(Category.id == cat_id).first()
            
            action = "skip"
            if existing:
                if replace_existing:
                    action = "update"
                    updates += 1
                    if not dry_run:
                        existing.section = section
                        existing.category = category
                        existing.subcategory = subcategory
                        # No updated_at on Category model currently, but that's fine
                else:
                    skips += 1
            else:
                action = "insert"
                inserts += 1
                if not dry_run:
                    new_cat = Category(
                        id=cat_id,
                        section=section,
                        category=category,
                        subcategory=subcategory
                    )
                    db.add(new_cat)
                    
            if dry_run:
                preview_rows.append({
                    'id': cat_id, 
                    'section': section, 
                    'cat': category, 
                    'sub': subcategory, 
                    'action': action
                })

        except Exception as e:
            errors.append({'row': idx, 'error': str(e)})

    if not dry_run:
        db.commit()
    
    return {
        'success': True,
        'total_rows': len(df),
        'inserted': inserts,
        'updated': updates,
        'skipped': skips,
        'errors': errors,
        'preview': preview_rows if dry_run else None
    }

