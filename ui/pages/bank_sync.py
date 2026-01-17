from nicegui import ui
import asyncio
from database.connection import SessionLocal
from database.models import AppSettings, StagedTransaction, Transaction
from services.simplefin import SimpleFin
from services.sync_manager import sync_simplefin_to_staging
from services.importer import apply_mapping_rules # Helper to run rules
from services.enrichment_service import enrich_transaction # Helper if available
from sqlalchemy import select, delete
from datetime import datetime

def bank_sync_page():
    # State
    class SyncState:
        def __init__(self):
            self.access_url = ""
            self.setup_token = ""
            self.lookback = 30 # days
            self.staged_rows = []
            self.selected_rows = []
            
    s = SyncState()

    # Load Settings
    def load_settings():
        with SessionLocal() as db:
            setting = db.scalar(select(AppSettings).where(AppSettings.key == 'simplefin_access_url'))
            if setting:
                s.access_url = setting.value
    
    load_settings()

    async def refresh_grid():
        with SessionLocal() as db:
            # Load pending
            rows = db.scalars(
                select(StagedTransaction)
                .where(StagedTransaction.status == 'pending')
                .order_by(StagedTransaction.date.desc())
            ).all()
            
            s.staged_rows = [{
                'id': r.id,
                'date': r.date.strftime('%Y-%m-%d'),
                'account': r.account_name,
                'description': r.description,
                'amount': r.amount,
                'external_id': r.external_id
            } for r in rows]
            
        grid.options['rowData'] = s.staged_rows
        grid.update()
        update_badges(len(s.staged_rows))

    def update_badges(count):
        # Update tab badge if we could access layout... for now just local label
        status_label.set_text(f"{count} Pending Transactions")

    # Actions
    async def claim_token():
        if not s.setup_token: return
        n = ui.notify("Claiming token...", type='ongoing')
        try:
            url = await asyncio.to_thread(SimpleFin.claim_setup_token, s.setup_token)
            
            # Save to DB
            with SessionLocal() as db:
                setting = db.scalar(select(AppSettings).where(AppSettings.key == 'simplefin_access_url'))
                if not setting:
                    setting = AppSettings(key='simplefin_access_url', component='simplefin')
                    db.add(setting)
                setting.value = url
                db.commit()
            
            s.access_url = url
            s.setup_token = "" # Clear for security
            n.dismiss()
            ui.notify("Successfully claimed and saved Access URL!", type='positive')
            
        except Exception as e:
            n.dismiss()
            ui.notify(f"Error: {e}", type='negative')

    async def run_sync():
        if not s.access_url:
            ui.notify("No Access URL configured.", type='warning')
            return
            
        n = ui.notify("Syncing with bank...", type='ongoing')
        try:
            stats = await asyncio.to_thread(sync_simplefin_to_staging, s.access_url, s.lookback)
            
            n.dismiss()
            
            if stats['errors']:
                 ui.notify(f"Sync completed with errors: {stats['errors']}", type='warning', timeout=0, close_button=True)
            else:
                 ui.notify(f"Sync Complete: {stats['staged']} new, {stats['fetched']} fetched.", type='positive')
            
            await refresh_grid()
            
        except Exception as e:
            n.dismiss()
            ui.notify(f"Critical Sync Error: {e}", type='negative')

    async def approve_selected():
        selected = await grid.get_selected_rows()
        if not selected: return
        
        n = ui.notify(f"Approving {len(selected)} transactions...", type='ongoing')
        
        try:
            with SessionLocal() as db:
                ids_to_process = [r['id'] for r in selected]
                
                # Fetch full objects
                staged_objs = db.scalars(
                    select(StagedTransaction).where(StagedTransaction.id.in_(ids_to_process))
                ).all()
                
                count = 0
                for staged in staged_objs:
                    # Create Real Transaction
                    tx = Transaction(
                        date=staged.date,
                        amount=staged.amount,
                        description=staged.description,
                        original_description=staged.description, # Save raw
                        account_name=staged.account_name,
                        simplefin_id=staged.external_id,
                        import_method='simplefin',
                        # Generate fingerprint for consistency
                        fingerprint=Transaction.generate_fingerprint(
                            staged.date.strftime('%Y-%m-%d'), 
                            staged.amount, 
                            staged.description
                        )
                    )
                    
                    # 1. Cleaning & Normalization (Regex)
                    # We can use the logic from importer.py if refactored, or call services.
                    # For now, minimal clear:
                    # tx.clean_description = ... (SimpleFin.clean_description(tx.description))
                    
                    # 2. Apply Mapping Rules (Standardization + Categorization)
                    # We need a helper for this that accepts a Transaction object
                    # For now, basic insertion. The "Enrichment" service usually runs after.
                    
                    db.add(tx)
                    db.delete(staged) # Remove from staging
                    count += 1
                
                db.commit()
                
                # Trigger Auto-Categorization on the new batch?
                # We can do this async or inline.
                
            n.dismiss()
            ui.notify(f"Approved {count} transactions.", type='positive')
            await refresh_grid()
            
        except Exception as e:
            n.dismiss()
            ui.notify(f"Error approving: {e}", type='negative')

    async def reject_selected():
        selected = await grid.get_selected_rows()
        if not selected: return
        
        with SessionLocal() as db:
            ids = [r['id'] for r in selected]
            # Hard delete for rejection? Or status='rejected'?
            # Req says "Deletes them"
            db.execute(delete(StagedTransaction).where(StagedTransaction.id.in_(ids)))
            db.commit()
            
        ui.notify(f"Rejected {len(selected)} transactions.", type='info')
        await refresh_grid()

    # --- UI Layout ---
    
    with ui.column().classes('w-full max-w-6xl mx-auto p-4 gap-6'):
        
        # Header & Config
        with ui.row().classes('w-full justify-between items-start'):
            ui.label("Bank Sync (SimpleFin)").classes('text-2xl font-bold')
            
            # Simple Config Area
            with ui.card().classes('p-4 bg-gray-50'):
                ui.label("Configuration").classes('font-bold mb-2')
                
                if not s.access_url:
                    ui.input("Setup Token", on_change=lambda e: setattr(s, 'setup_token', e.value)).classes('w-64')
                    ui.button("Claim Token", on_click=claim_token)
                else:
                    ui.label("Access URL Configured ✅").classes('text-green-600')
                    with ui.row().classes('items-center'):
                         ui.number("Lookback (Days)", value=s.lookback, min=1, max=365, 
                                   on_change=lambda e: setattr(s, 'lookback', int(e.value))).classes('w-24')
                         ui.button("Sync Now", on_click=run_sync, icon='sync').props('color=primary')

        ui.separator()
        
        # Inbox
        with ui.row().classes('w-full justify-between items-center'):
            status_label = ui.label("Loading...").classes('text-lg')
            
            with ui.row():
                ui.button("Reject Selected", on_click=reject_selected, icon='delete').props('color=red flat')
                ui.button("Approve Selected", on_click=approve_selected, icon='check').props('color=green')
        
        # Grid
        grid = ui.aggrid({
            'columnDefs': [
                {'headerName': 'Date', 'field': 'date', 'sortable': True, 'filter': True, 'checkboxSelection': True, 'headerCheckboxSelection': True},
                {'headerName': 'Account', 'field': 'account', 'sortable': True, 'filter': True},
                {'headerName': 'Description', 'field': 'description', 'sortable': True, 'filter': True, 'flex': 1},
                {'headerName': 'Amount', 'field': 'amount', 'sortable': True, 'filter': 'agNumberColumnFilter', 
                 'valueFormatter': "x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})",
                 'cellStyle': {'color': 'params.value < 0 ? "red" : "green"'}
                },
            ],
            'defaultColDef': {'resizable': True},
            'rowSelection': 'multiple',
            'pagination': True,
            'paginationPageSize': 20,
        }).classes('w-full h-96')
        
        # Init
        await refresh_grid()
