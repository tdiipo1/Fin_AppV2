from services.simplefin import SimpleFin
from database.connection import SessionLocal
from database.models import Transaction, StagedTransaction, AppSettings
from datetime import datetime, timedelta
from sqlalchemy import select

def sync_simplefin_to_staging(access_url: str, lookback_days: int = 30) -> dict:
    """
    Orchestrates the sync from SimpleFin -> StagedTransaction table.
    """
    stats = {"fetched": 0, "staged": 0, "skipped": 0, "errors": []}
    
    # 1. Determine Date Range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=lookback_days)
    
    # HARD CUTOFF: 2026-01-01
    hard_cutoff = datetime(2026, 1, 1)
    if start_date < hard_cutoff:
        start_date = hard_cutoff
        
    if start_date >= end_date:
        stats["errors"].append("Date range is entirely before 2026-01-01 cutoff.")
        return stats

    # 2. Fetch
    try:
        data = SimpleFin.fetch_transactions(access_url, start_date, end_date)
        acct_map = data['accounts']
        transactions = data['transactions']
        stats["fetched"] = len(transactions)
    except Exception as e:
        stats["errors"].append(f"Fetch failed: {str(e)}")
        return stats

    # 3. Process
    with SessionLocal() as db:
        # Pre-load existing external_ids to minimize DB hits
        # Get all external_ids from Transaction where simplefin_id is not null
        # And all from StagedTransaction
        
        existing_tx_ids = set(
            db.scalars(select(Transaction.simplefin_id).where(Transaction.simplefin_id != None)).all()
        )
        existing_staged_ids = set(
            db.scalars(select(StagedTransaction.external_id)).all()
        )
        
        new_staged = []
        
        for tx in transactions:
            # 4. Check Date Cutoff again (just in case API returned extra)
            # TX timestamp is usually unix epoch
            ts = int(tx.get('posted', 0))
            if ts == 0: ts = int(tx.get('transacted_at', 0)) # Fallback
            
            tx_date = datetime.fromtimestamp(ts)
            
            if tx_date < hard_cutoff:
                stats["skipped"] += 1
                continue
                
            # 5. Deduplication
            # external_id = account_id + transaction_id from SimpleFin
            ext_id = f"{tx['account_id']}-{tx['id']}"
            
            if ext_id in existing_tx_ids:
                stats["skipped"] += 1 # Already imported to real table
                continue
                
            if ext_id in existing_staged_ids:
                stats["skipped"] += 1 # Already pending approval
                continue
            
            # 6. Prepare Staged Object
            acct_name = acct_map.get(tx['account_id'], 'Unknown Account')
            amt = float(tx.get('amount', 0))
            # In SimpleFin, usually negative is expense, positive is income?
            # Or is it inverted? 
            # SimpleFin typically: Inflow is positive, Outflow is negative.
            # Our App: Income positive, Expense negative. Matches.
            
            desc = tx.get('description', '')
            if not desc: desc = tx.get('payee', 'Unknown')
            
            staged = StagedTransaction(
                external_id=ext_id,
                date=tx_date,
                description=desc,
                amount=amt,
                account_name=acct_name,
                status='pending'
            )
            
            db.add(staged)
            stats["staged"] += 1
            existing_staged_ids.add(ext_id) # Add to set to prevent dups within same batch
            
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            stats["errors"].append(f"Database commit failed: {str(e)}")
            
    return stats
