from nicegui import ui
import pandas as pd
import asyncio
from services.budget_service import BudgetService
from services.analytics import calculate_category_baselines
from database.connection import get_db, SessionLocal
from database.models import Category
from io import BytesIO

def budget_planning_page():
    
    # State
    class BudgetState:
        def __init__(self):
            self.budgets = {} # {scsc_id: amount}
            self.notes = {} # {scsc_id: note}
            self.baselines = {} # {scsc_id: amount}
            self.available_money = 5000.0 # Default
            self.categories = [] # List of Category objs
            self.sections = {} # {section: [categories]}
            self.modified_ids = set()
            self.loading = False

    s = BudgetState()

    def load_data():
        with SessionLocal() as db:
            # Load Categories
            cats = db.query(Category).all()
            s.categories = cats
            s.sections = {}
            for c in cats:
                if c.section not in s.sections:
                    s.sections[c.section] = []
                s.sections[c.section].append(c)

            # Load Budgets
            budget_dict = BudgetService.get_budget_dict(db)
            s.budgets = {k: b.amount for k, b in budget_dict.items()}
            s.notes = {k: b.note for k, b in budget_dict.items()}

            # Load Baselines
            s.baselines = calculate_category_baselines(db)
            
            s.modified_ids.clear()
            
    load_data()
    
    # --- Actions ---
    
    async def save_all():
        n = ui.notify("Saving budgets...", type='ongoing')
        try:
            with SessionLocal() as db:
                for scsc_id in s.modified_ids:
                    amt = s.budgets.get(scsc_id, 0.0)
                    note = s.notes.get(scsc_id, "")
                    BudgetService.update_budget(scsc_id, amt, note, db=db)
            
            s.modified_ids.clear()
            n.dismiss()
            ui.notify("Budgets saved successfully!", type='positive')
            render_summary.refresh() # Update surplus
            
        except Exception as e:
            n.dismiss()
            ui.notify(f"Error saving: {e}", type='negative')

    async def reset_changes():
        load_data()
        ui.notify("Discards reverted. Reloaded from DB.", type='info')
        render_grid.refresh()
        render_summary.refresh()
        
    def handle_budget_change(scsc_id, new_value):
        try:
            val = float(new_value)
        except:
            return # Invalid input
        
        if s.budgets.get(scsc_id) != val:
            s.budgets[scsc_id] = val
            s.modified_ids.add(scsc_id)
            render_summary.refresh() # Update surplus live

    def use_baseline(scsc_id, input_element):
        base = s.baselines.get(scsc_id, 0.0)
        s.budgets[scsc_id] = base
        s.modified_ids.add(scsc_id)
        input_element.value = base
        render_summary.refresh()

    async def handle_upload(e):
        try:
            content = e.content.read()
            df = pd.read_csv(BytesIO(content))
            
            # Run Import
            res = await asyncio.to_thread(BudgetService.import_budget_csv, df)
            
            if res['success']:
                msg = f"Imported: {res['inserted']} inserted, {res['updated']} updated."
                if res['errors']:
                    msg += f" {len(res['errors'])} errors."
                ui.notify(msg, type='positive' if not res['errors'] else 'warning')
                
                # Refresh UI
                await reset_changes()
            else:
                 ui.notify(f"Import Failed: {res['errors'][0]['reason']}", type='negative')
                 
        except Exception as ex:
             ui.notify(f"File Error: {ex}", type='negative')

    def download_csv():
        # Generate CSV in memory
        data = []
        for cat in s.categories:
            amt = s.budgets.get(cat.id, 0.0)
            data.append({
                'SCSC_ID': cat.id,
                'Section': cat.section,
                'Category': cat.category,
                'Subcategory': cat.subcategory,
                'Amount': amt
            })
        df = pd.DataFrame(data)
        ui.download(df.to_csv(index=False).encode('utf-8'), 'budget_export.csv')

    # --- UI Renders ---

    @ui.refreshable
    def render_summary():
        total_budgeted = sum(s.budgets.values())
        surplus = s.available_money - total_budgeted
        
        with ui.card().classes('w-full mb-4 p-4 bg-gray-50'):
            with ui.row().classes('w-full items-center justify-between'):
                with ui.column():
                    ui.label("Available Money").classes('text-sm text-gray-500')
                    
                    def set_avail(e):
                        try:
                            s.available_money = float(e.value)
                            render_summary.refresh()
                        except: pass
                        
                    ui.number(value=s.available_money, format='%.2f', on_change=set_avail).classes('text-xl font-bold')
                
                with ui.column():
                    ui.label("Total Budgeted").classes('text-sm text-gray-500')
                    ui.label(f"${total_budgeted:,.2f}").classes('text-xl font-bold')
                    
                with ui.column():
                    ui.label("Projected Surplus").classes('text-sm text-gray-500')
                    color = 'text-green-600' if surplus >= 0 else 'text-red-600'
                    ui.label(f"${surplus:,.2f}").classes(f'text-xl font-bold {color}')

    @ui.refreshable
    def render_grid():
        # Sort sections alphabetically
        sorted_sections = sorted(s.sections.keys())
        
        with ui.column().classes('w-full gap-2'):
            for section in sorted_sections:
                cats = s.sections[section]
                section_total = sum(s.budgets.get(c.id, 0.0) for c in cats)
                
                with ui.expansion(f"{section} (${section_total:,.0f})", icon='folder').classes('w-full bg-white border'):
                    with ui.column().classes('w-full p-2'):
                        for c in cats:
                            with ui.row().classes('w-full items-center gap-4 py-1 hover:bg-gray-50'):
                                # Label
                                sub = f" - {c.subcategory}" if c.subcategory else ""
                                ui.label(f"{c.category}{sub}").classes('w-1/3')
                                
                                # Input
                                current_val = s.budgets.get(c.id, 0.0)
                                inp = ui.number(value=current_val, format='%.2f', min=0)\
                                    .props('dense outlined suffix="$"')\
                                    .classes('w-32')\
                                    .on('change', lambda e, cid=c.id: handle_budget_change(cid, e.value))
                                
                                # Baseline Helper
                                base = s.baselines.get(c.id, 0.0)
                                if base > 0 and current_val == 0:
                                    ui.button(f"Avg: ${base:.0f}", on_click=lambda _, cid=c.id, i=inp: use_baseline(cid, i))\
                                      .props('flat dense size=sm color=grey') \
                                      .tooltip("Click to use 12-month average")
        
    # --- Page Layout ---
    
    with ui.column().classes('w-full max-w-5xl mx-auto p-4'):
        with ui.row().classes('w-full justify-between items-center'):
            ui.label("Budget Planning").classes('text-2xl font-bold')
            with ui.row():
                ui.button("Reset", on_click=reset_changes, icon='restart_alt').props('flat color=warning')
                ui.button("Save Changes", on_click=save_all, icon='save').props('color=primary')
        
        render_summary()
        
        with ui.tabs().classes('w-full') as tabs:
            tab_plan = ui.tab('Plan')
            tab_import = ui.tab('Import/Export')
            
        with ui.tab_panels(tabs, value=tab_plan).classes('w-full'):
            with ui.tab_panel(tab_plan):
                 render_grid()
                 
            with ui.tab_panel(tab_import):
                with ui.card().classes('w-full'):
                    ui.label("Import from CSV").classes('text-lg font-bold')
                    ui.upload(on_upload=handle_upload, auto_upload=True, label="Drag & Drop Budget CSV").classes('w-full')
                    ui.label("Expected format: SCSC_ID, Amount OR Section, Category, Subcategory, Amount").classes('text-sm text-gray-500 italic')
                    
                    ui.separator().classes('my-4')
                    
                    ui.label("Export").classes('text-lg font-bold')
                    ui.button("Download CSV", on_click=download_csv, icon='download')

