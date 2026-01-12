from sqlalchemy import func, extract, desc, case
from sqlalchemy.orm import Session
from database.models import Transaction, Category, Budget
from datetime import datetime
import pandas as pd

def get_monthly_net_income(db: Session, months=12, include_excluded=False):
    """
    Returns monthly Income vs Expense aggregation for the last `months` months.
    """
    # Group by Year-Month
    # SQLite strftime('%Y-%m', date)
    
    trunc_date = func.strftime('%Y-%m', Transaction.date).label('month')
    
    # Sum Incomes (Amount > 0)
    # Sum Expenses (Amount < 0)
    query = db.query(
        trunc_date,
        func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label('income'),
        func.sum(case((Transaction.amount < 0, Transaction.amount), else_=0)).label('expense')
    )
    
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)

    query = query.group_by(trunc_date).order_by(trunc_date.desc()).limit(months)
    
    results = query.all()
    # Reverse to show chronological
    return sorted(results, key=lambda x: x[0])

def get_net_income_range(db: Session, start_date, end_date, include_excluded=False):
    """
    Returns monthly Income vs Expense aggregation for a specific date range.
    """
    trunc_date = func.strftime('%Y-%m', Transaction.date).label('month')
    
    query = db.query(
        trunc_date,
        func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)).label('income'),
        func.sum(case((Transaction.amount < 0, Transaction.amount), else_=0)).label('expense')
    ).filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date
    )
    
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)

    query = query.group_by(trunc_date).order_by(trunc_date)
    return query.all()

def get_category_breakdown(db: Session, year: int, month: int, include_excluded=False):
    """
    Returns spending by Category for Sunburst chart.
    Hierarchical: Section -> Category -> Amount (Absolute expense)
    """
    # Filter for expenses only (< 0) in the given month
    
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    query = db.query(
        Category.section, 
        Category.category, 
        func.sum(Transaction.amount)
    ).join(Category, Transaction.category_id == Category.id)\
     .filter(Transaction.date >= start_date, Transaction.date < end_date)\
     .filter(Transaction.amount < 0)

    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)
     
    results = query.group_by(Category.section, Category.category).all()
     
    # Convert to list of dicts with abs amount
    data = []
    for r in results:
        data.append({
            'section': r[0],
            'category': r[1],
            'amount': abs(r[2])
        })
    return data

def get_budget_progress(db: Session, year: int, month: int, include_excluded=False):
    """
    Returns Section-level aggregated budget vs actuals.
    """
    # 1. Get Actuals (Expenses grouped by Section)
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
        
    actuals_query = db.query(
        Category.section,
        func.sum(Transaction.amount)
    ).join(Category, Transaction.category_id == Category.id)\
     .filter(Transaction.date >= start_date, Transaction.date < end_date)
     # .filter(Transaction.amount < 0) # Removed to allow refunds to offset spending

    if not include_excluded:
        actuals_query = actuals_query.filter(Transaction.is_excluded == False)

    actuals_res = actuals_query.group_by(Category.section).all()
     
    actual_map = {r[0]: abs(r[1]) for r in actuals_res}
    
    # 2. Get Budgets (grouped by Section)
    # Budget is linked to Category.
    # Note: Budgets in DB are monthly category targets naturally.
    # Assuming the Budget table holds the MONTHLY target amount.
    budget_res = db.query(
        Category.section,
        func.sum(Budget.amount)
    ).join(Category, Budget.scsc_id == Category.id)\
     .group_by(Category.section).all()
     
    budget_map = {r[0]: r[1] for r in budget_res}
    
    # 3. Merge
    all_sections = set(actual_map.keys()) | set(budget_map.keys())
    
    progress_data = []
    for section in sorted(list(all_sections)):
        spent = actual_map.get(section, 0.0)
        target = budget_map.get(section, 0.0)
        
        # Avoid showing section if both are effectively zero (floating point safety)
        if spent < 0.01 and target < 0.01:
            continue
            
        progress_data.append({
            'section': section,
            'spent': spent,
            'budget': target,
            'percent': (spent / target * 100) if target > 0 else 0
        })
        
    return progress_data

def get_top_merchants(db: Session, start_date=None, end_date=None, limit=10, include_excluded=False):
    """
    Returns top expenses by merchant (description).
    Aggregates by cleanse_description if available, else description.
    """
    merchant_name = func.coalesce(Transaction.clean_description, Transaction.description).label('merchant')
    
    query = db.query(
        merchant_name,
        func.sum(Transaction.amount).label('total_amount'),
        func.count(Transaction.id).label('tx_count')
    )
    
    # Filter only Expenses (< 0)
    # query = query.filter(Transaction.amount < 0)  <-- REMOVE THIS to include refunds in aggregation

    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
        
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)
        
    # Filter for Net Expenses (Sum < 0) using HAVING
    # This allows refunds (positive) to offset spending (negative).
    query = query.having(func.sum(Transaction.amount) < 0)
    
    # Sort by total amount ascending (most negative first)
    query = query.order_by(func.sum(Transaction.amount).asc()).limit(limit)
    
    results = query.all()
    # Convert to list of dicts
    return [{'merchant': r[0], 'amount': r[1], 'count': r[2]} for r in results]

def get_merchant_history(db: Session, merchant_name, include_excluded=False):
    """
    Get full history for a specific merchant name (matching clean or raw).
    """
    query = db.query(Transaction)
    
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)

    # Match against clean or description
    query = query.filter(
        func.coalesce(Transaction.clean_description, Transaction.description) == merchant_name
    )
    
    query = query.order_by(Transaction.date.desc())
    return query.all()


def get_monthly_transactions(db: Session, year: int, month: int, type: str, include_excluded=False):
    """
    Fetch transactions for a specific month and type (Income/Expense).
    Reverting to pure Amount Sign logic as requested by user.
    Income = Amount > 0
    Expense = Amount < 0
    """
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
        
    query = db.query(Transaction).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date
    )
    
    if type == 'Income':
        query = query.filter(Transaction.amount > 0)
    elif type == 'Expense':
        query = query.filter(Transaction.amount < 0)
        
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)
        
    return query.order_by(Transaction.date.desc()).all()


def get_top_merchants(db: Session, start_date=None, end_date=None, limit=10, include_excluded=False):
    """
    Returns top expenses by merchant (including refund offsets).
    Logic: Sum ALL amounts per merchant. Filter for Next Expenses (< 0).
    """
    merchant_name = func.coalesce(Transaction.clean_description, Transaction.description).label('merchant')
    
    # 1. Calculate Sum
    query = db.query(
        merchant_name,
        func.sum(Transaction.amount).label('total_amount'),
        func.count(Transaction.id).label('tx_count')
    )
    
    if start_date:
        query = query.filter(Transaction.date >= start_date)
    if end_date:
        query = query.filter(Transaction.date <= end_date)
        
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)
        
    # Group First
    query = query.group_by(merchant_name)
    
    # Filter for Net Expenses (Sum < 0) using HAVING
    # This allows refunds (positive) to offset spending (negative).
    query = query.having(func.sum(Transaction.amount) < 0)
    
    # Sort by total amount ascending (most negative first)
    query = query.order_by(func.sum(Transaction.amount).asc()).limit(limit)
    
    results = query.all()
    # Convert to list of dicts
    return [{'merchant': r[0], 'amount': r[1], 'count': r[2]} for r in results]


def get_category_breakdown(db: Session, year, month, include_excluded=False):
    """
    Returns spending breakdown by Category/Section for a given month.
    """
    # SQLite Month extraction 
    # Use between dates for better index usage
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
    
    # We want to show NET Spending per category.
    # Logic: Sum all amounts per category. 
    # If Sum is Negative (Net Expense), show it (as positive value).
    # If Sum is Positive (Net Income), usually we exclude it from "Spending Breakdown".
    # PREVIOUSLY: likely filtering only amount < 0.
    
    # Let's check logic:
    # return db.query(Category.section, Category.category, func.sum(Transaction.amount)) ...
    
    query = db.query(
        Category.section,
        Category.category,
        func.sum(Transaction.amount).label('net_amount')
    ).join(Category, Transaction.category_id == Category.id)
    
    # Date Filter
    query = query.filter(Transaction.date >= start_date, Transaction.date < end_date)
    
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)
    
    # Grouping
    query = query.group_by(Category.section, Category.category)
    
    results = query.all()
    
    data = []
    for r in results:
        # r = (section, category, sum_amount)
        # Spending is negative amount.
        net_val = r[2]
        
        # If net_val is negative, it's spending. Convert to positive for chart.
        # If net_val is positive (Refunds > Purchases), it's "Negative Spending". 
        # Sunburst doesn't like negative values. 
        # We usually filter out Net Income categories from Spending Charts or cap at 0.
        if net_val < 0:
            data.append({
                'section': r[0],
                'category': r[1],
                'amount': abs(net_val)
            })
            
    return data
