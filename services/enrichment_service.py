from sqlalchemy.orm import Session
from sqlalchemy import or_
from database.models import Transaction, MerchantMap, CategoryMap, Category
import re

def clean_description_regex(raw_desc: str) -> str:
    """
    Cleans a raw bank description using regex to remove common noise.
    Example: "WHOLE FOODS MKT #2341" -> "WHOLE FOODS MKT"
    """
    if not raw_desc:
        return ""
    
    # 1. Remove common noise
    # Remove Store Numbers (e.g. #123, # 123)
    val = re.sub(r'#\s*\d+', '', raw_desc)
    # Remove specific location codes if needed (simple version)
    # Remove 'Debit Card Purchase' etc (Generic)
    
    # Simple cleaning: Strip extra spaces
    val = " ".join(val.split())
    
    # Additional logic can be added here
    # e.g., Title Case
    return val.strip().title()

def enrich_transaction(db: Session, transaction: Transaction) -> Transaction:
    """
    Enrich a transaction with merchant mapping and category mapping.
    """
    # Step 1: Clean description if not present
    if not transaction.clean_description:
        transaction.clean_description = clean_description_regex(transaction.raw_description or transaction.description)
    
    # Step 2: Merchant mapping
    # Look for exact match or contains
    # Since we want performance, we check exact first, then "contains" logic if needed.
    # The prompt suggests a combined query.
    
    merchant_record = None
    
    # Try exact match on raw first (fastest)
    if transaction.raw_description:
         merchant_record = db.query(MerchantMap).filter(MerchantMap.raw_description == transaction.raw_description).first()
    
    # If not found, try fuzzy/clean match
    if not merchant_record and transaction.clean_description:
        merchant_record = db.query(MerchantMap).filter(
            or_(
                MerchantMap.raw_description == transaction.clean_description,
                MerchantMap.standardized_merchant.ilike(transaction.clean_description) 
            )
        ).first()

    if merchant_record:
        transaction.standardized_merchant = merchant_record.standardized_merchant
        transaction.merchant_map_id = merchant_record.id
    else:
        # Fallback: Use clean description as standardized merchant
        transaction.standardized_merchant = transaction.clean_description

    # Step 3: Category mapping (lookup by standardized merchant)
    # We look up using the standardized merchant name in the category map
    category_record = db.query(CategoryMap).filter(
        CategoryMap.unmapped_description.ilike(transaction.standardized_merchant)
    ).first()
    
    if category_record:
        transaction.category_id = category_record.scsc_id # Map to category_id (scsc_id alias)
        transaction.category_map_id = category_record.id
    else:
        # Check if we didn't map merchant, maybe raw/clean desc matches a category map directly?
        # (Optional, but good fallback)
        pass
        
    return transaction

def enrich_all_new_transactions(db: Session):
    """Enrich all transactions that haven't been mapped yet."""
    # Find transactions without standardized_merchant
    txs = db.query(Transaction).filter(
        or_(
            Transaction.standardized_merchant == None,
            Transaction.category_id == None
        )
    ).all()
    
    count = 0
    for t in txs:
        enrich_transaction(db, t)
        count += 1
    
    db.commit()
    return count
