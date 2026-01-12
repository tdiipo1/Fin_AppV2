from nicegui import ui
from database.connection import get_db
from database.models import Transaction, Category
from sqlalchemy.orm import joinedload
from datetime import datetime

# Helper to format category for dropdown
def format_category(c):
    return f"{c.section} > {c.category}" + (f" > {c.subcategory}" if c.subcategory else "")

def content():
    ui.label('Transactions').classes('text-3xl font-bold text-slate-800 mb-6')
    
    # 1. Fetch Data
    db = next(get_db())
    
    # Get all categories for the dropdown
    categories = db.query(Category).order_by(Category.section, Category.category).all()
    
    # Nicer Approach:
    # We will pass the 'Category Label' to the grid. On edit, we pick from Labels. 
    # When saving, we look up the ID from the Label.
    cat_label_to_id = {format_category(c): c.id for c in categories}
    cat_labels = sorted(list(cat_label_to_id.keys()))
    
    # Fetch Transactions
    txs = db.query(Transaction).options(joinedload(Transaction.category)).order_by(Transaction.date.desc()).all()
    
    row_data = []
    for t in txs:
        cat_label = format_category(t.category) if t.category else "Uncategorized"
        
        row_data.append({
            'id': t.id,
            'date': t.date.strftime('%Y-%m-%d'),
            'raw_desc': t.raw_description or t.description,
            'clean_desc': t.standardized_merchant or t.clean_description or t.description,
            'amount': t.amount,
            'category': cat_label, # Display Label
            'section': t.category.section if t.category else 'Uncategorized',
            'account': t.account_name or 'Manual',
            'data_source': t.source_file or 'Unknown'
        })

    # 2. Export Features
    csv_dialog = ui.dialog().classes('w-full')
    
    def open_export_dialog():
        csv_dialog.clear()
        
        # Available columns to select
        # Use simple mapping: Label -> Field Key
        cols = {
            'Date': 'date',
            'Merchant (Raw)': 'raw_desc',
            'Merchant (Clean)': 'clean_desc',
            'Amount': 'amount',
            'Category': 'category',
            'Section': 'section',
            'Account': 'account',
            'Data Source': 'data_source'
        }
        
        selected_cols = {k: True for k in cols} # Default all selected
        
        with csv_dialog, ui.card().classes('min-w-[400px] p-6'):
            ui.label('Export to CSV').classes('text-xl font-bold mb-4')
            ui.label('Select columns to include:').classes('text-sm text-gray-500 mb-2')
            
            # Checkboxes container
            checks = {}
            with ui.column().classes('w-full gap-1 mb-6'):
                for label, key in cols.items():
                    checks[key] = ui.checkbox(label, value=True)
            
            async def run_export():
                # Gather selected keys
                keys = [key for key, chk in checks.items() if chk.value]
                if not keys:
                    ui.notify('Select at least one column', type='warning')
                    return
                
                # AgGrid Export
                # We use columnKeys param to filter columns.
                # fileName defaults to 'export.csv' but can be set.
                ts = datetime.now().strftime('%Y-%m-%d_%H%M')
                params = {
                    'fileName': f'transactions_{ts}.csv',
                    'columnKeys': keys
                }
                
                await grid.run_grid_method('exportDataAsCsv', params)
                csv_dialog.close()
                ui.notify('Export started', type='positive')

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=csv_dialog.close).props('flat')
                ui.button('Download CSV', on_click=run_export).classes('bg-blue-600 text-white')
        
        csv_dialog.open()

    # 3. Grid Definitions
    default_col_def = {
        'sortable': True,
        'filter': True,
        'resizable': True,
        'suppressMenu': True
    }
    
    column_defs = [
        {'headerName': 'Hidden ID', 'field': 'id', 'hide': True},
        {'headerName': 'Date', 'field': 'date', 'width': 120, 'sort': 'desc'},
        {'headerName': 'Merchant (Raw)', 'field': 'raw_desc', 'width': 200, 'tooltipField': 'raw_desc'},
        {'headerName': 'Merchant (Clean)', 'field': 'clean_desc', 'width': 200, 'editable': True},
        {'headerName': 'Amount', 'field': 'amount', 'width': 110, 
         'type': 'numericColumn', 
         'valueFormatter': "value.toLocaleString('en-US', {style: 'currency', currency: 'USD'})"},
        
        # Category Dropdown
        {'headerName': 'Category', 'field': 'category', 'width': 350, 'editable': True,
         'cellEditor': 'agSelectCellEditor',
         'cellEditorParams': {
             'values': cat_labels
         }
        },
        
        {'headerName': 'Section', 'field': 'section', 'width': 150}, # Read-only derived
        {'headerName': 'Account', 'field': 'account', 'width': 150},
        {'headerName': 'Data Source', 'field': 'data_source', 'width': 200},
    ]

    async def handle_cell_value_change(e):
        # e.args is {rowId, colId, newValue, oldValue, data, ...}
        # Note: 'data' contains the whole row with the NEW value already.
        row = e.args['data']
        tx_id = row['id']
        field = e.args['colId']
        new_val = e.args['newValue']
        
        if field == 'clean_desc':
            # Update Description
            db_tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
            if db_tx:
                db_tx.standardized_merchant = new_val
                # db_tx.clean_description = new_val # Legacy field, maybe keep in sync?
                db.commit()
                ui.notify('Merchant updated')
                
        elif field == 'category':
            # Reverse lookup ID from Label
            new_cat_id = cat_label_to_id.get(new_val)
            if new_cat_id:
                db_tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
                if db_tx:
                    db_tx.category_id = new_cat_id
                    db.commit()
                    
                    # Refresh Section column in UI? 
                    # The grid won't auto-update dependent columns unless we force it or update row data.
                    # We can re-fetch category to get section.
                    new_cat = db.query(Category).filter(Category.id == new_cat_id).first()
                    section = new_cat.section if new_cat else ""
                    
                    # Update local grid data via API.
                    # Note: We need to use execute_javascript or similar because e.args['api'] is a proxy handle.
                    # But NiceGUI `run_grid_method` works on the whole grid, not specific rows easily without Key.
                    # Easier: Just notify user. The user sees the change in 'Category' column immediately.
                    # 'Section' won't update until refresh. That's acceptable for V2 MVP.
                    ui.notify(f'Category updated to {new_val}')
            else:
                ui.notify("Invalid Category", type='warning')

    async def delete_selected_rows():
        rows = await grid.get_selected_rows()
        if not rows:
            ui.notify("No rows selected")
            return
            
        ids_to_del = [r['id'] for r in rows]
        
        # Delete from DB
        db.query(Transaction).filter(Transaction.id.in_(ids_to_del)).delete(synchronize_session=False)
        db.commit()
        
        # Remove from Grid
        grid.run_grid_method('applyTransaction', {'remove': rows})
        ui.notify(f"Deleted {len(rows)} transactions")

    # 4. Render UI
    with ui.row().classes('w-full gap-4 mb-4 justify-between'):
        ui.button('Delete Selected', on_click=delete_selected_rows, icon='delete').props('color=red-600 outline')
        ui.button('Export to CSV', on_click=open_export_dialog, icon='download').classes('ml-auto bg-green-600 text-white')
    
    grid = ui.aggrid({
        'columnDefs': column_defs,
        'defaultColDef': default_col_def,
        'rowData': row_data,
        'rowSelection': 'multiple',
        'pagination': True,
        'paginationPageSize': 20,
        'domLayout': 'autoHeight'
    }).classes('w-full').on('cellValueChanged', handle_cell_value_change)
    
