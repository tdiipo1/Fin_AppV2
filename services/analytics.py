from sqlalchemy import func, extract, desc, case
from sqlalchemy.orm import Session
from database.models import Transaction, Category, Budget
from datetime import datetime, timedelta
import pandas as pd

def get_monthly_net_income(db: Session, months=12, include_excluded=False):
    """
    Returns monthly Income vs Expense aggregation for the last `months` months.
    """
    trunc_date = func.strftime('%Y-%m', Transaction.date).label('month')
    
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
    Returns spending by Category for Sunburst chart (Net Expenses only).
    """
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)

    query = db.query(
        Category.section,
        Category.category,
        func.sum(Transaction.amount).label('net_amount')
    ).join(Category, Transaction.category_id == Category.id)
    
    query = query.filter(Transaction.date >= start_date, Transaction.date < end_date)
    
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)
    
    query = query.group_by(Category.section, Category.category)
    
    results = query.all()
    
    data = []
    for r in results:
        net_val = r[2]
        if net_val < 0:
            data.append({
                'section': r[0],
                'category': r[1],
                'amount': abs(net_val)
            })
    return data

def get_top_merchants(db: Session, start_date=None, end_date=None, limit=10, include_excluded=False):
    """
    Returns top expenses by merchant (grouping by clean_description if available).
    """
    merchant_name = func.coalesce(Transaction.clean_description, Transaction.description).label('merchant')
    
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
        
    query = query.group_by(merchant_name)
    query = query.having(func.sum(Transaction.amount) < 0)
    query = query.order_by(func.sum(Transaction.amount).asc()).limit(limit)
    
    results = query.all()
    return [{'merchant': r[0], 'amount': r[1], 'count': r[2]} for r in results]

def get_merchant_history(db: Session, merchant_name, include_excluded=False):
    """
    Get full history for a specific merchant name.
    """
    query = db.query(Transaction)
    
    if not include_excluded:
        query = query.filter(Transaction.is_excluded == False)

    query = query.filter(
        func.coalesce(Transaction.clean_description, Transaction.description) == merchant_name
    )
    
    query = query.order_by(Transaction.date.desc())
    return query.all()

def get_monthly_transactions(db: Session, year: int, month: int, type: str, include_excluded=False):
    """
    Fetch transactions for a specific month and type (Income/Expense).
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

# --- Budget Analytics ---

def calculate_category_baselines(db: Session, months: int = 12) -> dict:
    """
    Calculates Annual Spending Baseline (Monthly Average * 12).
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30*months)
    
    # Sum spending (negative amounts) groupings by scsc_id
    query = db.query(
        Transaction.category_id,
        func.sum(Transaction.amount)
    ).filter(
        Transaction.amount < 0,
        Transaction.date >= start_date,
        Transaction.category_id != None
    ).group_by(Transaction.category_id)
    
    results = query.all()
    
    baselines = {}
    for r in results:
        total_spend = abs(r[1])
        avg_monthly_spend = total_spend / months
        
        # Annualize
        annual_projection = avg_monthly_spend * 12
        
        # Round to nearest 100 as requested
        rounded_annual = round(annual_projection / 100) * 100
        
        baselines[r[0]] = rounded_annual
        
    return baselines

def get_budget_comparison(db: Session, start_date: datetime, end_date: datetime, include_excluded=False):
    """
    Compares Actual Spending vs Budget Logic.
    Budget amounts in DB are ANNUAL.
    We must scale them to the requested time period.
    """
    # Calculate Time Factor (Ratio of Year)
    days = (end_date - start_date).days
    year_ratio = days / 365.0
    
    # If it's roughly 1 month (28-31 days), force 1/12
    if 28 <= days <= 31:
        year_ratio = 1.0 / 12.0
    
    # 1. Get Actual Spending by Category for the period
    actuals_query = db.query(
        Category.id.label('scsc_id'),
        Category.section,
        Category.category,
        func.sum(Transaction.amount).label('actual_amount')
    ).join(Category, Transaction.category_id == Category.id)\
     .filter(Transaction.date >= start_date, Transaction.date <= end_date)\
     .filter(Transaction.amount < 0)
    
    if not include_excluded:
        actuals_query = actuals_query.filter(Transaction.is_excluded == False)
        
    actuals_rows = actuals_query.group_by(Category.id).all()
    
    actuals_map = {r.scsc_id: abs(r.actual_amount) for r in actuals_rows}
    category_info = {r.scsc_id: {'section': r.section, 'category': r.category} for r in actuals_rows}
    
    # 2. Get All Budgets (ANNUAL amounts)
    budgets = db.query(Budget).all()
    budget_map = {b.scsc_id: b.amount for b in budgets}
    
    all_categories = db.query(Category).all()
    for c in all_categories:
        if c.id not in category_info:
            category_info[c.id] = {'section': c.section, 'category': c.category}
            
    # 3. Merge
    all_ids = set(actuals_map.keys()) | set(budget_map.keys())
    
    data = []
    
    for scsc_id in all_ids:
        annual_budget = budget_map.get(scsc_id, 0.0)
        period_budget = annual_budget * year_ratio
        
        actual = actuals_map.get(scsc_id, 0.0)
        info = category_info.get(scsc_id, {'section': 'Unknown', 'category': 'Unknown'})
        
        variance = period_budget - actual
        variance_pct = (variance / period_budget * 100) if period_budget > 0 else 0
        
        status = 'On Track'
        if variance < 0:
            status = 'Over Budget'
        elif variance > 0 and period_budget > 0:
            status = 'Under Budget'
            
        data.append({
            'scsc_id': scsc_id,
            'section': info['section'],
            'category': info['category'],
            'budgeted': period_budget, 
            'annual_budget': annual_budget,
            'actual': actual,
            'variance': variance,
            'variance_pct': variance_pct,
            'status': status
        })
        
    return data

def get_budget_progress(db: Session, year: int, month: int, include_excluded=False):
    """
    Returns Section-level aggregated budget vs actuals for a specific month.
    This uses ANNUAL budget / 12.
    """
    start_date = datetime(year, month, 1)
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
        
    # 1. Get Actuals (Expenses grouped by Section)
    actuals_query = db.query(
        Category.section,
        func.sum(Transaction.amount)
    ).join(Category, Transaction.category_id == Category.id)\
     .filter(Transaction.date >= start_date, Transaction.date < end_date)\
     .filter(Transaction.amount < 0)

    if not include_excluded:
        actuals_query = actuals_query.filter(Transaction.is_excluded == False)

    actuals_res = actuals_query.group_by(Category.section).all()
     
    actual_map = {r[0]: abs(r[1]) for r in actuals_res}
    
    # 2. Get Budgets (grouped by Section) - ANNUAL
    budget_res = db.query(
        Category.section,
        func.sum(Budget.amount)
    ).join(Category, Budget.scsc_id == Category.id)\
     .group_by(Category.section).all()
     
    # Convert Annual to Monthly
    budget_map = {r[0]: (r[1] / 12) for r in budget_res}
    
    # 3. Merge
    all_sections = set(actual_map.keys()) | set(budget_map.keys())
    
    progress_data = []
    for section in sorted(list(all_sections)):
        spent = actual_map.get(section, 0.0)
        target = budget_map.get(section, 0.0)
        
        if spent < 0.01 and target < 0.01:
            continue
            
        progress_data.append({
            'section': section,
            'spent': spent,
            'budget': target,
            'percent': (spent / target * 100) if target > 0 else 0
        })
        
    return progress_data
