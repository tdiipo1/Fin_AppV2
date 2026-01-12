from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from database.models import Transaction, Category
from datetime import date
from typing import List, Dict, Optional

def get_top_entities(
    db: Session,
    start_date: date,
    end_date: date,
    limit: int = 10,
    sort_by: str = 'amount',
    group_by: str = 'Merchant'
) -> List[Dict]:
    """
    Get top entities (Merchants, Categories, Sections) by spending volume.
    """
    # Determine grouping entity
    if group_by == 'Category':
        group_col = Category.category
        label_key = 'category'
    elif group_by == 'Subcategory':
        group_col = Category.subcategory
        label_key = 'subcategory'
    elif group_by == 'Section':
        group_col = Category.section
        label_key = 'section'
    else: # Merchant
        group_col = Transaction.standardized_merchant
        label_key = 'standardized_merchant'

    query = db.query(
        group_col.label('entity_name'),
        func.sum(Transaction.amount).label('total_amount'),
        func.count(Transaction.id).label('transaction_count'),
        func.avg(Transaction.amount).label('avg_transaction')
    ).join(
        Category,
        Transaction.category_id == Category.id, 
        isouter=True
    ).filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.is_excluded == False
    )
    
    # Handle NULLs (e.g. unmapped merchants or categories)
    # We filter them out or include them appropriately
    
    query = query.group_by(group_col).having(func.sum(Transaction.amount) < 0)
    
    if sort_by == 'count':
        query = query.order_by(desc('transaction_count'))
    else:
        # Sort by magnitude of spending (most negative first)
        query = query.order_by(func.sum(Transaction.amount).asc())
    
    results = query.limit(limit).all()
    
    data = []
    for r in results:
        name = r.entity_name or f"Unspecified {group_by}"
        # Convert net negative amount to positive for display (Spending)
        net_spend = abs(float(r.total_amount or 0)) 
        data.append({
            'standardized_merchant': name, # Keep key for grid compatibility, or rename grid col
            'entity_type': group_by,
            'total_amount': net_spend,
            'transaction_count': int(r.transaction_count or 0),
            'avg_transaction': abs(float(r.avg_transaction or 0))
        })
    return data

def get_entity_time_series(
    db: Session,
    entity_name: str,
    entity_type: str,
    start_date: date,
    end_date: date,
    group_by: str = 'month'
) -> List[Dict]:
    """
    Get spending trend for a specific entity.
    """
    if group_by == 'day':
        group_expr = func.date(Transaction.date)
    elif group_by == 'year':
        group_expr = func.strftime('%Y', Transaction.date)
    else: # month
        group_expr = func.strftime('%Y-%m', Transaction.date)

    query = db.query(
        group_expr.label('period'),
        func.sum(func.abs(Transaction.amount)).label('total_amount'),
        func.count(Transaction.id).label('count')
    ).join(
        Category,
        Transaction.category_id == Category.id, 
        isouter=True
    ).filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.is_excluded == False,
        Transaction.amount < 0
    )
    
    # Filter by Entity
    if entity_type == 'Category':
        query = query.filter(Category.category == entity_name)
    elif entity_type == 'Subcategory':
        query = query.filter(Category.subcategory == entity_name)
    elif entity_type == 'Section':
        query = query.filter(Category.section == entity_name)
    else:
        query = query.filter(Transaction.standardized_merchant == entity_name)
        
    query = query.group_by(group_expr).order_by(group_expr)
    
    return [
        {'date': r[0], 'amount': float(r[1]), 'count': int(r[2])}
        for r in query.all()
    ]

def get_entity_transactions(
    db: Session,
    entity_name: str,
    entity_type: str,
    start_date: date,
    end_date: date,
    limit: Optional[int] = 500
) -> List[Dict]:
    """
    Get raw transactions for drill-down.
    """
    query = db.query(Transaction).join(
        Category,
        Transaction.category_id == Category.id, 
        isouter=True
    ).filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        Transaction.is_excluded == False
    )

    if entity_type == 'Category':
        query = query.filter(Category.category == entity_name)
    elif entity_type == 'Subcategory':
        query = query.filter(Category.subcategory == entity_name)
    elif entity_type == 'Section':
        query = query.filter(Category.section == entity_name)
    else:
        # For merchant, include raw name variations if possible
        query = query.filter(
             or_(
                Transaction.standardized_merchant == entity_name,
                Transaction.clean_description == entity_name
            )
        )
        
    query = query.order_by(Transaction.date.desc())
    
    if limit:
        query = query.limit(limit)
    
    return [
        {
            'id': t.id,
            'date': t.date.strftime('%Y-%m-%d'),
            'raw_description': t.raw_description or t.description,
            'amount': t.amount,
            'source': t.source_file or t.account_name
        }
        for t in query.all()
    ]
