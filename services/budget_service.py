from sqlalchemy.orm import Session
from sqlalchemy import select, delete
from database.models import Budget, Category
from database.connection import get_db, SessionLocal
import pandas as pd
from datetime import datetime
import logging

class BudgetService:
    @staticmethod
    def get_all_budgets(db: Session = None):
        """
        Get all budget entries joined with categories.
        Returns a dictionary keyed by scsc_id for easy lookup, or a list.
        """
        # If no DB session is provided, create a temporary one
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True
            
        try:
            stmt = select(Budget).order_by(Budget.scsc_id)
            results = db.execute(stmt).scalars().all()
            return results
        finally:
            if close_session:
                db.close()

    @staticmethod
    def get_budget_dict(db: Session = None):
        """Returns {scsc_id: BudgetObj}"""
        budgets = BudgetService.get_all_budgets(db)
        return {b.scsc_id: b for b in budgets}

    @staticmethod
    def update_budget(scsc_id: str, amount: float, note: str = None, db: Session = None) -> Budget:
        """
        Update or Create a budget entry for a specific Category ID.
        """
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True
            
        try:
            stmt = select(Budget).where(Budget.scsc_id == scsc_id)
            budget = db.execute(stmt).scalars().first()
            
            if budget:
                budget.amount = float(amount)
                if note is not None:
                    budget.note = note
                budget.updated_at = datetime.utcnow()
            else:
                # Validate scsc_id exists?
                cat_stmt = select(Category).where(Category.id == scsc_id)
                cat = db.execute(cat_stmt).scalars().first()
                if not cat:
                    raise ValueError(f"Category {scsc_id} does not exist.")
                
                budget = Budget(
                    scsc_id=scsc_id,
                    amount=float(amount),
                    note=note,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(budget)
            
            db.commit()
            db.refresh(budget)
            return budget
        except Exception as e:
            db.rollback()
            raise e
        finally:
            if close_session:
                db.close()

    @staticmethod
    def import_budget_csv(df: pd.DataFrame, dry_run: bool = False, db: Session = None) -> dict:
        """
        Imports budget from a DataFrame.
        Expected columns: 
        - Option A: 'SCSC_ID', 'Amount'
        - Option B: 'Section', 'Category', 'Subcategory', 'Amount'
        """
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True
            
        results = {
            "success": True,
            "total_rows": len(df),
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "warnings": [],
            "preview": None
        }

        try:
            # 1. Normalize Columns
            df.columns = [c.strip().lower() for c in df.columns]
            
            # Map common column names
            col_map = {
                'scsc_id': 'scsc_id', 'id': 'scsc_id',
                'section': 'section',
                'category': 'category',
                'subcategory': 'subcategory',
                'amount': 'amount', 'budget': 'amount'
            }
            df.rename(columns=col_map, inplace=True)

            # 2. Get All Categories for Lookup
            categories = db.execute(select(Category)).scalars().all()
            
            # Map (Section, Cat, Subcat) -> SCSC_ID
            cat_map = {}
            for c in categories:
                key = (
                    c.section.strip().lower(), 
                    c.category.strip().lower(), 
                    (c.subcategory or "").strip().lower()
                )
                cat_map[key] = c.id
            
            # Set of valid IDs
            valid_ids = {c.id for c in categories}
            
            to_commit = []
            
            # 3. Process Rows
            for index, row in df.iterrows():
                try:
                    scsc_id = None
                    amount = 0.0
                    
                    # Parse Amount
                    try:
                        val = str(row.get('amount', 0)).replace('$', '').replace(',', '')
                        amount = float(val)
                        if amount < 0:
                            results["warnings"].append(f"Row {index}: Negative budget amount cast to positive or allowed?")
                    except:
                        results["errors"].append({"row": index, "reason": "Invalid amount"})
                        continue

                    # Resolve ID
                    if 'scsc_id' in row and pd.notna(row['scsc_id']):
                        cand_id = str(row['scsc_id']).strip()
                        if cand_id in valid_ids:
                            scsc_id = cand_id
                    
                    if not scsc_id:
                        # Try lookup
                        s = str(row.get('section', '')).strip().lower()
                        c = str(row.get('category', '')).strip().lower()
                        # Subcategory handles NaN
                        sub = str(row.get('subcategory', ''))
                        if sub == 'nan': sub = ""
                        sub = sub.strip().lower()
                        
                        key = (s, c, sub)
                        if key in cat_map:
                            scsc_id = cat_map[key]
                    
                    if not scsc_id:
                        results["skipped"] += 1
                        results["errors"].append({"row": index, "reason": "Could not match Category/SCSC_ID"})
                        continue
                        
                    # Prepare Object
                    # Check if exists for stats
                    existing = db.execute(select(Budget).where(Budget.scsc_id == scsc_id)).scalars().first()
                    is_update = existing is not None
                    
                    if dry_run:
                        # For preview, we just tally
                        if is_update:
                            results["updated"] += 1
                        else:
                            results["inserted"] += 1
                    else:
                        BudgetService.update_budget(scsc_id, amount, db=db)
                        if is_update:
                            results["updated"] += 1
                        else:
                            results["inserted"] += 1

                except Exception as e:
                    results["errors"].append({"row": index, "reason": str(e)})
            
            if dry_run:
                results["preview"] = df.head() # Simple preview

        except Exception as e:
            results["success"] = False
            results["errors"].append({"reason": f"Global Error: {str(e)}"})
        finally:
            if close_session:
                db.close()
                
        return results

    @staticmethod
    def get_budget_summary(db: Session = None):
        """
        Aggregate budget by Section.
        """
        close_session = False
        if db is None:
            db = SessionLocal()
            close_session = True
        try:
            # Join Budget and Category
            stmt = select(Category.section, Budget.amount)\
                   .join(Budget, Category.id == Budget.scsc_id)
            rows = db.execute(stmt).all()
            
            summary = {}
            for section, amount in rows:
                summary[section] = summary.get(section, 0) + amount
            return summary
        finally:
            if close_session:
                db.close()
