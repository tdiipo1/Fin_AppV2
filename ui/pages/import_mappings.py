from nicegui import ui
from database.connection import get_db
from database.models import Category, MerchantMap, CategoryMap, Transaction
from services.csv_importer import import_merchant_map_csv, import_category_map_csv, import_category_taxonomy_csv
import os
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict
import asyncio

# Ensure uploads directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'uploads')
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

def content():
    ui.label('Mapping Center').classes('text-3xl font-bold text-slate-800 mb-6')
    
    # --- Shared Upload Handlers (from original file) ---
    state = {
        'taxonomy_file': None,
        'merchant_file': None,
        'category_file': None
    }
    
    async def handle_upload(e, key):
        filename = f"{key}_upload.csv"
        filepath = os.path.join(UPLOAD_DIR, filename)
        try:
            content = e.file.read()
            from inspect import iscoroutine
            if iscoroutine(content): content = await content
            with open(filepath, 'wb') as f: f.write(content)
            state[f'{key}_file'] = filepath
            ui.notify(f"File staged: {e.file.name}")
        except Exception as ex: ui.notify(f"Upload failed: {ex}", type='negative')

    async def run_import(key, func, **kwargs):
        if not state.get(f'{key}_file'): return
        db = next(get_db())
        try:
            res = func(db, state[f'{key}_file'], replace_existing=True, **kwargs)
            
            with ui.dialog() as d, ui.card():
                ui.label(f"Import Result ({'Dry Run' if kwargs.get('dry_run') else 'Commit'})").classes('text-xl font-bold')
                if res.get('success'):
                    ui.label(f"Total: {res.get('total_rows', 0)}, Inserts: {res.get('inserted', 0)}, Updates: {res.get('updated', 0)}")
                    if kwargs.get('dry_run'):
                        async def do_commit():
                            d.close()
                            ui.notify('Committing changes...', type='info')
                            await run_import(key, func, dry_run=False)
                        
                        ui.button('Commit', on_click=do_commit).classes('bg-green-600 text-white')
                else:
                    ui.label(f"Error: {res.get('error')}").classes('text-red-500')
                ui.button('Close', on_click=d.close)
            d.open()
        except Exception as e: ui.notify(str(e), type='negative')

    # --- TABS ---
    with ui.tabs().classes('w-full') as tabs:
        tab_import = ui.tab('Data Import')
        tab_taxonomy = ui.tab('Taxonomy Editor')
        tab_merchants = ui.tab('Merchant Mappings')
        tab_categories = ui.tab('Keyword Mappings')

    with ui.tab_panels(tabs, value=tab_import).classes('w-full mt-4 bg-transparent'):
        
        # --- TAB 1: IMPORTS (Preserved) ---
        with ui.tab_panel(tab_import):
            with ui.card().classes('w-full mb-4 p-4 border-l-4 border-blue-500'):
                ui.label('1. Taxonomy (Categories)').classes('font-bold')
                with ui.row().classes('items-center gap-4'):
                    ui.upload(on_upload=lambda e: handle_upload(e, 'taxonomy'), auto_upload=True).props('accept=.csv').classes('w-64')
                    ui.button('Preview Import', on_click=lambda: run_import('taxonomy', import_category_taxonomy_csv, dry_run=True)).props('outline')

            with ui.card().classes('w-full mb-4 p-4 border-l-4 border-green-500'):
                ui.label('2. Merchant Map').classes('font-bold')
                with ui.row().classes('items-center gap-4'):
                    ui.upload(on_upload=lambda e: handle_upload(e, 'merchant'), auto_upload=True).props('accept=.csv').classes('w-64')
                    ui.button('Preview Import', on_click=lambda: run_import('merchant', import_merchant_map_csv, dry_run=True)).props('outline')

            with ui.card().classes('w-full mb-4 p-4 border-l-4 border-purple-500'):
                ui.label('3. Category Keyword Map').classes('font-bold')
                with ui.row().classes('items-center gap-4'):
                    ui.upload(on_upload=lambda e: handle_upload(e, 'category'), auto_upload=True).props('accept=.csv').classes('w-64')
                    ui.button('Preview Import', on_click=lambda: run_import('category', import_category_map_csv, dry_run=True)).props('outline')

        # --- TAB 2: TAXONOMY EDITOR ---
        with ui.tab_panel(tab_taxonomy):
            taxonomy_editor()

        # --- TAB 3: MERCHANT EDITOR ---
        with ui.tab_panel(tab_merchants):
            merchant_editor()

        # --- TAB 4: CATEGORY EDITOR ---
        with ui.tab_panel(tab_categories):
            category_mapping_editor()

# --- EDITOR COMPONENTS ---

# --- HELPER: Auto-ID ---
def generate_next_category_id(db: Session) -> str:
    # Find max ID starting with SCSC
    cats = db.query(Category.id).all() 
    max_num = 0
    for (cid,) in cats:
        if cid.startswith('SCSC') and len(cid) > 4:
            try:
                num = int(cid[4:])
                if num > max_num: max_num = num
            except: pass
    
    new_num = max_num + 1
    return f"SCSC{new_num:04d}"

def taxonomy_editor():
    ui.label('Edit Category Hierarchy').classes('text-lg font-bold mb-2')
    ui.label('IDs are system-managed. Modify Section, Category, Subcategory as needed.').classes('text-sm text-gray-500 mb-4')

    # Container for Grid
    grid_container = ui.column().classes('w-full h-[600px]')
    
    # Dialog for New Category
    new_cat_dialog = ui.dialog().classes('w-full')
    
    def open_add_dialog():
        new_cat_dialog.clear()
        
        db = next(get_db())
        next_id = generate_next_category_id(db)
        
        # Get existing unique values for autocomplete
        all_cats = db.query(Category).all()
        sections = sorted(list(set([c.section for c in all_cats if c.section])))
        categories_list = sorted(list(set([c.category for c in all_cats if c.category])))
        
        with new_cat_dialog, ui.card().classes('min-w-[400px] p-6'):
            ui.label('New Category').classes('text-xl font-bold mb-4')
            
            ui.input('ID', value=next_id).props('readonly').classes('w-full bg-gray-100 mb-2')
            
            # Autocomplete inputs using ui.select with new-value-mode or straightforward inputs with autocomplete logic
            # Simpler: Use ui.input with autocomplete options via a menu or datalist? 
            # NiceGUI's ui.select with use_input=True allows typing and selecting, but enforcing "new" is tricky.
            # Best for "Section": Select existing or type new. ui.select(..., new_value_mode='add-unique')
            
            section_select = ui.select(
                options=sections, 
                with_input=True, 
                new_value_mode='add-unique',
                label='Section'
            ).classes('w-full mb-2')
            
            category_select = ui.select(
                options=categories_list, 
                with_input=True, 
                new_value_mode='add-unique',
                label='Category'
            ).classes('w-full mb-2')

            subcat_input = ui.input('Subcategory (Optional)').classes('w-full mb-4')
            
            def commit_new():
                if not section_select.value or not category_select.value:
                    ui.notify('Section and Category are required', type='negative')
                    return
                
                try:
                    new_cat = Category(
                        id=next_id,
                        section=section_select.value,
                        category=category_select.value,
                        subcategory=subcat_input.value
                    )
                    db.add(new_cat)
                    db.commit()
                    ui.notify(f'Created {next_id}', type='positive')
                    new_cat_dialog.close()
                    load_data() # Refresh grid
                except Exception as e:
                    ui.notify(f'Error: {e}', type='negative')

            with ui.row().classes('w-full justify-end mt-4 gap-2'):
                ui.button('Cancel', on_click=new_cat_dialog.close).props('flat color=grey')
                ui.button('Create', on_click=commit_new).classes('bg-green-600 text-white')
        
        new_cat_dialog.open()

    def load_data():
        grid_container.clear()
        
        # Use proper session handling
        from database.connection import SessionLocal
        with SessionLocal() as db:
            cats = db.query(Category).all()
            rows = [{'id': c.id, 'section': c.section, 'category': c.category, 'subcategory': c.subcategory} for c in cats]
        
        # Track changes client-side
        # Dictionary to store dirty rows by ID
        dirty_rows = {}
        
        def handle_cell_edit(e):
            if e.args and 'data' in e.args:
                r = e.args['data']
                dirty_rows[r['id']] = r

        async def save_changes():
            if not dirty_rows:
                ui.notify('No changes to save', type='info')
                return

            with SessionLocal() as db:
                try:
                    # Naive Upsert for edits
                    updated_ids = list(dirty_rows.keys())
                    cats_to_update = db.query(Category).filter(Category.id.in_(updated_ids)).all()
                    
                    count = 0
                    for cat in cats_to_update:
                        new_data = dirty_rows.get(cat.id)
                        if new_data:
                            cat.section = new_data['section']
                            cat.category = new_data['category']
                            cat.subcategory = new_data['subcategory']
                            count += 1
                    
                    db.commit()
                    dirty_rows.clear()
                    ui.notify(f'Taxonomy saved ({count} updates).', type='positive')
                except Exception as e:
                    db.rollback()
                    ui.notify(f'Error saving: {e}', type='negative')

        with grid_container:
            grid = ui.aggrid({
                'columnDefs': [
                    {'field': 'id', 'width': 100, 'editable': False, 'headerName': 'ID', 'sortable': True},
                    {'field': 'section', 'width': 150, 'editable': True, 'filter': True},
                    {'field': 'category', 'width': 150, 'editable': True, 'filter': True},
                    {'field': 'subcategory', 'width': 150, 'editable': True, 'filter': True}
                ],
                'rowData': rows,
                'defaultColDef': {'sortable': True, 'resizable': True, 'filter': True},
                'pagination': True,
                'paginationPageSize': 100
            }).classes('h-full w-full')
            
            grid.on('cellValueChanged', handle_cell_edit)
        
            with ui.row().classes('mt-4 gap-4'):
                ui.button('Add New Category', on_click=open_add_dialog).classes('bg-green-600 text-white')
                ui.button('Save Changes', on_click=save_changes).classes('bg-blue-600 text-white')

    load_data()


def merchant_editor():
    ui.label('Merchant Normalization Rules').classes('text-lg font-bold mb-2')
    ui.label('Map raw bank descriptions to clean merchant names.').classes('text-sm text-gray-500 mb-4')

    # Controls
    with ui.row().classes('w-full items-center justify-between mb-2'):
        show_unmapped_only = ui.switch('Show Only Unmapped / New')
        # Trigger reload on switch change
        show_unmapped_only.on('update:model-value', lambda: reload_grid())
    
    # Use a generic container for content to avoid button shifting
    content_area = ui.column().classes('w-full')
    
    # State tracking
    pending_changes = {} 
    grid_ref = {'instance': None} # To access grid from outside

    async def reload_grid():
        # Capture state
        filter_model = None
        if grid_ref['instance']:
            try:
                filter_model = await grid_ref['instance'].run_grid_method('getFilterModel')
            except Exception:
                # Ignore if grid is not ready or API fails
                pass
        
        await load_data(restore_filters=filter_model)

    async def load_data(restore_filters=None):
        content_area.clear()
        
        # Use proper session handling
        from database.connection import SessionLocal
        with SessionLocal() as db:
            # 1. Fetch Existing Maps
            maps = db.query(MerchantMap).all()
            # Fetch ALL standardized merchants for autocomplete
            all_standardized_merchants = [m.standardized_merchant for m in maps if m.standardized_merchant]
            all_standardized_merchants = sorted(list(set(all_standardized_merchants)))
            
            # 2. Fetch "Ghost" Transactions (Unmapped in Transaction table)
            existing_raws = {m.raw_description for m in maps}
            
            ghosts = db.query(Transaction.raw_description)\
                    .filter(Transaction.standardized_merchant == None)\
                    .distinct().all()
            
            # Merge Sets
            data_list = []
            
            # Add existing maps first
            for m in maps:
                data_list.append({
                    'id': m.id,
                    'raw_description': m.raw_description,
                    'standardized_merchant': m.standardized_merchant,
                    'status': 'Saved'
                })
                
            # Add ghosts (only if distinct and not covered)
            for (raw_desc,) in ghosts:
                if raw_desc and raw_desc not in existing_raws:
                    data_list.append({
                        'id': None, # Marker for new
                        'raw_description': raw_desc,
                        'standardized_merchant': '',
                        'status': 'Unmapped Transaction'
                    })
        
        # Merged Pending Changes
        # Updates display to reflect unsaved edits
        for row in data_list:
            key = row.get('id') if row.get('id') is not None else row.get('raw_description')
            if key in pending_changes:
                row['standardized_merchant'] = pending_changes[key]['standardized_merchant']
                row['status'] = 'Pending Save'
        
        # Filter Logic
        if show_unmapped_only.value:
            # Check effective val
            data_list = [d for d in data_list if not d['standardized_merchant'] or not d['standardized_merchant'].strip()]

        # Dialog for editing Merchant
        edit_merchant_dialog = ui.dialog().classes('w-full')
        
        def open_merchant_dialog(row_data):
            edit_merchant_dialog.clear()
            if not row_data: return
            
            # If we have unsaved pending changes for this row, use them
            key = row_data.get('id') if row_data.get('id') is not None else row_data.get('raw_description')
            if key in pending_changes:
                current_val = pending_changes[key].get('standardized_merchant', '')
            else:
                current_val = row_data.get('standardized_merchant', '')
            
            # Ensure valid value for ui.select
            if not current_val:
                current_val = None

            with edit_merchant_dialog, ui.card().classes('min-w-[500px] p-6'):
                ui.label(f"Normalize: {row_data.get('raw_description')}").classes('text-lg font-bold mb-4')
                
                # Autocomplete Input
                # We use ui.select with new_value_mode='add-unique' to allow typing NEW or selecting EXISTING
                std_select = ui.select(
                    options=all_standardized_merchants,
                    value=current_val,
                    with_input=True,
                    new_value_mode='add-unique',
                    label='Clean Name (Select or Type New)'
                ).classes('w-full mb-6')
                
                def commit_edit():
                    new_val = std_select.value
                    if not new_val:
                        ui.notify("Value cannot be empty", type='warning')
                        return
                    
                    # Update local state
                    row_data['standardized_merchant'] = new_val
                    
                    # Add to pending changes queue
                    pending_changes[key] = row_data
                    
                    edit_merchant_dialog.close()
                    ui.notify("Change staged.", type='positive')
                    # Keep position, just refresh data
                    reload_grid()

                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cancel', on_click=edit_merchant_dialog.close).props('flat')
                    ui.button('OK', on_click=commit_edit).classes('bg-blue-600 text-white')
            
            edit_merchant_dialog.open()

        def handle_cell_click(e):
             # Only handle clicks on specific columns or rows?
             # For now, any click on the row allows editing the normalized merchant
             try:
                 if e.args and 'data' in e.args and e.args['data']:
                     # Ignode clicks on the checkbox column (colId usually has specific name or index)
                     if e.args.get('colId') == 'raw_description' and e.args.get('event', {}).get('target', {}).get('className', '').find('ag-checkbox') >= 0:
                         return

                     open_merchant_dialog(e.args['data'])
                 else:
                     # Fallback for unmapped rows where data structure might be slightly different or delayed
                     # Sometimes e.args['data'] is empty if the row is still rendering?
                     pass
             except Exception as ex:
                 ui.notify(f"Click Error: {ex}", type='negative')

        async def save_changes():
            if not pending_changes:
                ui.notify('No changes to save', type='info')
                return

            import time
            from sqlalchemy.exc import OperationalError
            max_retries = 3
            
            for attempt in range(max_retries):
                gen = get_db()
                db = next(gen)
                try:
                    # We iterate our tracked changes instead of getting all rows
                    updates_to_process = list(pending_changes.values())
                    tx_updated_count = 0
                    
                    # 1. Update Existing
                    # Filter for items with an ID
                    updates_existing = {r['id']: r for r in updates_to_process if r.get('id') is not None}
                    
                    if updates_existing:
                        existing = db.query(MerchantMap).filter(MerchantMap.id.in_(updates_existing.keys())).all()
                        for m in existing:
                            new_data = updates_existing.get(m.id)
                            if new_data:
                                m.standardized_merchant = new_data['standardized_merchant']
                                # Note: raw_desc shouldn't change for existing usually, but we allow it
                                m.raw_description = new_data['raw_description']
                                
                                # Update Transactions for this Merchant
                                cc = db.query(Transaction).filter(
                                    Transaction.raw_description == m.raw_description
                                ).update({Transaction.standardized_merchant: m.standardized_merchant}, synchronize_session=False)
                                tx_updated_count += cc

                    # 2. Insert New
                    # Items where id is None but clean name is provided
                    new_items = [r for r in updates_to_process if r.get('id') is None and r.get('standardized_merchant', '').strip()]
                    
                    for item in new_items:
                        # Double check existence to prevent race condition/duplicates
                        exists = db.query(MerchantMap).filter(MerchantMap.raw_description == item['raw_description']).first()
                        if not exists:
                            new_map = MerchantMap(
                                raw_description=item['raw_description'],
                                standardized_merchant=item['standardized_merchant']
                            )
                            db.add(new_map)
                            
                            cc = db.query(Transaction).filter(
                                Transaction.raw_description == item['raw_description']
                            ).update({Transaction.standardized_merchant: item['standardized_merchant']}, synchronize_session=False)
                            tx_updated_count += cc
                        else:
                            # Fallback: Update existing
                            exists.standardized_merchant = item['standardized_merchant']
                            
                            cc = db.query(Transaction).filter(
                                Transaction.raw_description == exists.raw_description
                            ).update({Transaction.standardized_merchant: item['standardized_merchant']}, synchronize_session=False)
                            tx_updated_count += cc
                    
                    db.commit()
                    ui.notify(f'Saved rules & updated {tx_updated_count} transactions.', type='positive')
                    
                    # Clear queue and reload
                    pending_changes.clear()
                    break
                except OperationalError as e:
                    db.rollback()
                    if "locked" in str(e) and attempt < max_retries - 1:
                        time.sleep(0.2)
                        continue
                    else:
                        ui.notify(f'Database Locked Today: {e}', type='negative')
                        break
                except Exception as e:
                    db.rollback()
                    ui.notify(f'Error saving: {e}', type='negative')
                    break
                finally:
                    db.close()
            
            # Refresh grid outside of lock
            await reload_grid()

        with content_area:
            grid = ui.aggrid({
                'columnDefs': [
                    {'field': 'id', 'hide': True},
                    {'field': 'status', 'headerName': 'Status', 'width': 120, 'pinned': 'left'},
                    {'field': 'raw_description', 'headerName': 'Raw Description Match', 'editable': False, 'width': 400, 
                     'checkboxSelection': True, 'headerCheckboxSelection': True, 'headerCheckboxSelectionFilteredOnly': True},
                    {'field': 'standardized_merchant', 'headerName': 'Clean Name', 'editable': False, 'width': 400}
                ],
                'rowData': data_list,
                'defaultColDef': {'sortable': True, 'resizable': True, 'filter': True},
                'rowSelection': 'multiple', 
                'pagination': True,
                'paginationPageSize': 100
            }).classes('w-full h-[600px]')
            
            grid_ref['instance'] = grid

            # Restore filters if passed
            if restore_filters:
                grid.run_grid_method('setFilterModel', restore_filters)
            
            # Use Cell Click to edit single
            grid.on('cellClicked', handle_cell_click)

            async def handle_edit_selected():
                rows = await grid.get_selected_rows()
                if not rows:
                    ui.notify("No rows selected", type='warning')
                    return
                
                # Open Multi-Edit Dialog
                edit_merchant_dialog.clear()
                first_row = rows[0]
                
                with edit_merchant_dialog, ui.card().classes('min-w-[500px] p-6'):
                    ui.label(f"Batch Normalize ({len(rows)} items)").classes('text-lg font-bold mb-4')
                    ui.label(f"Example: {first_row.get('raw_description')}").classes('text-xs text-gray-500 mb-4')
                    

                    # Ensure value is valid for ui.select, otherwise set to None
                    current_val = first_row.get('standardized_merchant')
                    if not current_val:
                        current_val = None

                    std_select = ui.select(
                        options=all_standardized_merchants,
                        value=current_val,
                        with_input=True,
                        new_value_mode='add-unique',
                        label='Clean Name for ALL selected'
                    ).classes('w-full mb-6')
                    
                    def commit_batch():
                        new_val = std_select.value
                        if not new_val:
                            ui.notify("Value cannot be empty", type='warning')
                            return
                        
                        count = 0
                        for row in rows:
                            key = row.get('id') if row.get('id') is not None else row.get('raw_description')
                            # Update local row data
                            row['standardized_merchant'] = new_val
                            # Stage change
                            pending_changes[key] = row
                            count += 1
                        
                        edit_merchant_dialog.close()
                        ui.notify(f"Staged {count} updates.", type='positive')
                        reload_grid()

                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('Cancel', on_click=edit_merchant_dialog.close).props('flat')
                        ui.button('Apply to Selection', on_click=commit_batch).classes('bg-blue-600 text-white')
                
                edit_merchant_dialog.open()


            async def handle_clear_all():
                # We define the button variable to access it later
                clear_btn = None
                
                async def do_clear():
                    if clear_btn:
                        clear_btn.props('loading')
                        clear_btn.disable()
                    
                    # Optional: Show a sticky notification or spinner
                    n = ui.notify("Clearing Associations... This may take a moment.", type='ongoing')
                    
                    try:
                        def _clear_op():
                            from database.connection import SessionLocal
                            with SessionLocal() as db_sess:
                                db_sess.query(MerchantMap).delete()
                                db_sess.query(Transaction).update({Transaction.standardized_merchant: None}, synchronize_session=False)
                                db_sess.commit()
                                return True

                        await asyncio.to_thread(_clear_op)
                        try: n.dismiss()
                        except: pass
                        ui.notify("All merchant associations cleared.", type='positive')
                        reload_grid()
                        clear_dialog.close()
                    except Exception as e:
                        try: n.dismiss()
                        except: pass
                        if clear_btn:
                            clear_btn.props(remove='loading')
                            clear_btn.enable()
                        ui.notify(f"Error: {e}", type='negative')

                clear_dialog = ui.dialog()
                with clear_dialog, ui.card():
                    ui.label("WARNING: Clear All Associations?").classes('text-lg font-bold text-red-600')
                    ui.label("This will delete ALL merchant normalizing rules and reset transaction names.").classes('mb-4')
                    with ui.row().classes('justify-end'):
                        ui.button('Cancel', on_click=clear_dialog.close).props('flat')
                        clear_btn = ui.button('Clear All', on_click=do_clear).classes('bg-red-600 text-white')
                clear_dialog.open()

            async def handle_download_csv():
                # For merchant mapping, we export raw_description and standardized_merchant
                # We can use grid export
                grid_params = {'fileName': 'merchant_mappings.csv'}
                try:
                    await grid.run_grid_method('exportDataAsCsv', grid_params)
                except Exception:
                    pass

            with ui.row().classes('gap-4 mt-4'):
                ui.button('Save Changes', on_click=save_changes).classes('bg-blue-600 text-white')
                ui.button('Edit Selected', on_click=handle_edit_selected).props('outline')
                with ui.row().classes('ml-auto gap-2'):
                    ui.button('Download CSV', on_click=handle_download_csv).props('flat icon=download')
                    ui.button('Clear All', on_click=handle_clear_all).classes('bg-red-100 text-red-800').props('flat icon=delete')


    # Initial load
    ui.timer(0.1, lambda: reload_grid(), once=True)

def category_mapping_editor():
    ui.label('Keyword Category Rules').classes('text-lg font-bold mb-2')
    ui.label('Map transaction descriptions to specific Categories.').classes('text-sm text-gray-500 mb-4')

    # Controls
    with ui.row().classes('w-full items-center justify-between mb-2'):
        show_unmapped_only = ui.switch('Show Uncategorized Transactions')
        show_unmapped_only.on('update:model-value', lambda: load_data())

    grid_container = ui.column().classes('w-full h-96')
    
    # Dialog for Editing Mapping
    edit_dialog = ui.dialog().classes('w-full')
    cat_grid_ref = {'instance': None}

    def load_data():
        grid_container.clear()
        db = next(get_db())
        
        # Common Data
        cats = db.query(Category).all()
        cat_options = {c.id: f"{c.section} > {c.category}" + (f" > {c.subcategory}" if c.subcategory else "") for c in cats}
        
        mode_unmapped = show_unmapped_only.value
        
        rows = []
        if mode_unmapped:
            # Mode A: Show Uncategorized Transactions (Aggregated)
            # Find transactions with category_id IS NULL
            # Group by raw_description (or description?)
            # Let's use raw_description as that's what we usually map against.
            # But wait, transactions might have clean_description or standardized_merchant.
            # Keyword map matches 'unmapped_description'.
            
            # Helper to prioritise a display name
            # We will list distinct RAW descriptions that have NO category.
            # We limit to top 500 or paging? UI handles paging.
            
            uncat_tx = db.query(Transaction.raw_description, func.count(Transaction.id))\
                         .filter(Transaction.category_id == None)\
                         .group_by(Transaction.raw_description)\
                         .all()
            
            for (desc, count) in uncat_tx:
                if not desc: continue
                rows.append({
                    'id': None, # New
                    'unmapped_description': desc,
                    'scsc_id': None, # Use None for no category
                    'category_label': 'Uncategorized',
                    'count': count
                })
        else:
            # Mode B: Show Existing Rules
            maps = db.query(CategoryMap).all()
            for m in maps:
                rows.append({
                    'id': m.id,
                    'unmapped_description': m.unmapped_description,
                    'scsc_id': m.scsc_id,
                    'category_label': cat_options.get(m.scsc_id, m.scsc_id),
                    'count': 'Rule'
                })
        
        # Explicitly close the read session to prevent locks
        db.close()

        def open_edit_dialog(row_data):
            try:
                edit_dialog.clear()
                if not row_data: return
                
                # Safe Value Getting
                current_id = row_data.get('scsc_id')
                
                # Robust handling of ID
                if current_id == '' or str(current_id).lower() == 'nan':
                    current_id = None
                
                # Validate against options
                if current_id is not None and current_id not in cat_options:
                    current_id = None

                keyword_val = row_data.get('unmapped_description') or ''
                
                with edit_dialog, ui.card().classes('min-w-[500px] p-6'):
                    title = 'Edit Mapping Rule' if row_data.get('id') else 'Create New Rule'
                    ui.label(title).classes('text-xl font-bold mb-4')
                    
                    if row_data.get('count') != 'Rule':
                         ui.label(f"Found {row_data.get('count')} transactions matching this description.").classes('text-xs text-gray-500 mb-2')
                    
                    desc_input = ui.input('Contains Keyword', value=keyword_val).classes('w-full mb-4')
                    
                    # Category Selector
                    cat_select = ui.select(
                        options=cat_options, 
                        value=current_id, 
                        with_input=True,
                        label='Assign Category'
                    ).classes('w-full mb-6')
                    
                    async def save_single_edit():
                        new_desc = desc_input.value
                        new_cat_id = cat_select.value
                        if not new_desc or not new_cat_id:
                            ui.notify('Both fields are required', type='warning')
                            return
                        
                        # Use protected session to prevent locks
                        from database.connection import SessionLocal
                        from sqlalchemy.exc import OperationalError
                        import asyncio
                        
                        max_retries = 5 # Increase retries
                        success = False
                        
                        for attempt in range(max_retries):
                            try:
                                # Run DB operations in thread to avoid blocking UI loop
                                def _db_op():
                                    with SessionLocal() as db_sess:
                                        # Unified Merge Logic
                                        mapping = None
                                        
                                        # 1. Try to find existing by ID (Edit Mode)
                                        if row_data.get('id'):
                                            mapping = db_sess.query(CategoryMap).filter(CategoryMap.id == row_data['id']).first()
                                        
                                        # 2. If not found by ID (Create Mode) or ID was invalid, try by Description
                                        if not mapping:
                                            mapping = db_sess.query(CategoryMap).filter(CategoryMap.unmapped_description == new_desc).first()

                                        msg = ""
                                        if mapping:
                                            mapping.unmapped_description = new_desc
                                            mapping.scsc_id = new_cat_id
                                            msg = f"Updated rule for '{new_desc}'"
                                        else:
                                            mapping = CategoryMap(
                                                unmapped_description=new_desc,
                                                scsc_id=new_cat_id
                                            )
                                            db_sess.add(mapping)
                                            msg = f"Created rule for '{new_desc}'"
                                            
                                        # AUTO-APPLY
                                        count_updated = db_sess.query(Transaction).filter(
                                            Transaction.raw_description.ilike(f"%{new_desc}%"),
                                            Transaction.category_id == None
                                        ).update({Transaction.category_id: new_cat_id}, synchronize_session=False)
                                        
                                        db_sess.commit()
                                        return msg, count_updated

                                # Execute in thread
                                msg, count_updated = await asyncio.to_thread(_db_op)
                                
                                # UI Updates (Main Thread)
                                ui.notify(msg, type='positive')
                                if count_updated > 0:
                                    ui.notify(f"Applied to {count_updated} transactions.", type='positive')
                                    
                                success = True
                                break # Exit retry loop
                                
                            except OperationalError as e:
                                if "locked" in str(e) and attempt < max_retries - 1:
                                    await asyncio.sleep(0.5) # Non-blocking sleep, slightly longer
                                    continue
                                else:
                                    ui.notify(f"Database Locked: {e}", type='negative')
                                    break
                            except Exception as e:
                                ui.notify(f"Error: {e}", type='negative')
                                break
                        
                        if success:
                            edit_dialog.close()
                            # Simply reload
                            load_data()

                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('Cancel', on_click=edit_dialog.close).props('flat')
                        ui.button('Save', on_click=save_single_edit).classes('bg-blue-600 text-white')
                
                edit_dialog.open()
            except Exception as e:
                ui.notify(f"Cannot open dialog: {e}", type='negative')

        with grid_container:
            # We make columns read-only to force using the Dialog for ID safety.
            col_defs = [
                {'field': 'id', 'hide': True},
                {'field': 'unmapped_description', 'headerName': 'Contains Keyword', 'editable': False, 'width': 300, 
                 'checkboxSelection': True, 'headerCheckboxSelection': True, 'headerCheckboxSelectionFilteredOnly': True},
            ]
            
            if mode_unmapped:
                 col_defs.append({'field': 'count', 'headerName': 'Tx Count', 'width': 100})
            
            col_defs.extend([
                {'field': 'category_label', 'headerName': 'Assigned Category', 'editable': False, 'width': 400},
                {'field': 'scsc_id', 'headerName': 'ID', 'editable': False, 'width': 100}
            ])

            grid = ui.aggrid({
                'columnDefs': col_defs,
                'rowData': rows,
                'defaultColDef': {'sortable': True, 'resizable': True, 'filter': True},
                'pagination': True,
                'rowSelection': 'multiple',
            }).classes('h-[600px] w-full')
            
            cat_grid_ref['instance'] = grid

            async def handle_row_click(e):
                # Ignore checkbox clicks which are handled by AgGrid selection
                if e.args and 'colId' in e.args and e.args.get('event', {}).get('target', {}).get('className', '').find('ag-checkbox') >= 0:
                    return
                # Handle cell click
                if e.args and 'data' in e.args and e.args['data']:
                    open_edit_dialog(e.args['data'])

            grid.on('cellClicked', handle_row_click)
            
            async def handle_batch_edit():
                rows = await grid.get_selected_rows()
                if not rows:
                    ui.notify("No rows selected", type='warning')
                    return
                
                # Multi-edit Dialog
                # Reuse edit_dialog but with batch logic? Or clear and custom setup.
                # Let's clean and setup specifically for batch.
                edit_dialog.clear()
                
                with edit_dialog, ui.card().classes('min-w-[500px] p-6'):
                    ui.label(f'Batch Category Assign ({len(rows)} items)').classes('text-xl font-bold mb-4')
                    ui.label("Assign the same category to all selected rules/keywords.").classes('text-sm text-gray-500 mb-4')
                    
                    cat_select = ui.select(
                        options=cat_options, 
                        with_input=True,
                        label='Assign Category'
                    ).classes('w-full mb-6')
                    
                    async def save_batch():
                        new_cat_id = cat_select.value
                        if not new_cat_id:
                            ui.notify('Category is required', type='warning')
                            return
                        
                        from database.connection import SessionLocal
                        import asyncio
                        
                        def _batch_op():
                            with SessionLocal() as db_sess:
                                updated_count = 0
                                tx_updated_total = 0
                                
                                for row in rows:
                                    mapping = None
                                    desc = row.get('unmapped_description')
                                    
                                    # Find or Create
                                    if row.get('id'):
                                         mapping = db_sess.query(CategoryMap).filter(CategoryMap.id == row['id']).first()
                                    
                                    if not mapping and desc:
                                         mapping = db_sess.query(CategoryMap).filter(CategoryMap.unmapped_description == desc).first()
                                    
                                    if mapping:
                                        mapping.scsc_id = new_cat_id
                                        updated_count += 1
                                    elif desc:
                                        mapping = CategoryMap(
                                            unmapped_description=desc,
                                            scsc_id=new_cat_id
                                        )
                                        db_sess.add(mapping)
                                        updated_count += 1
                                    
                                    # Auto-apply to transactions
                                    if desc:
                                        cc = db_sess.query(Transaction).filter(
                                            Transaction.raw_description.ilike(f"%{desc}%"),
                                            Transaction.category_id == None
                                        ).update({Transaction.category_id: new_cat_id}, synchronize_session=False)
                                        tx_updated_total += cc
                                
                                db_sess.commit()
                                return updated_count, tx_updated_total

                        ui.notify("Processing batch update...", type='info')
                        rule_count, tx_count = await asyncio.to_thread(_batch_op)
                        
                        ui.notify(f"Updated {rule_count} rules and applied to {tx_count} transactions.", type='positive')
                        edit_dialog.close()
                        load_data()

                    with ui.row().classes('w-full justify-end gap-2'):
                        ui.button('Cancel', on_click=edit_dialog.close).props('flat')
                        ui.button('Apply Batch', on_click=save_batch).classes('bg-blue-600 text-white')
                
                edit_dialog.open()


            async def handle_clear_all():
                clear_btn = None
                
                async def do_clear():
                    if clear_btn:
                        clear_btn.props('loading')
                        clear_btn.disable()

                    n = ui.notify("Clearing Associations... This may take a moment.", type='ongoing')
                    
                    try:
                        def _clear_op():
                            from database.connection import SessionLocal
                            with SessionLocal() as db_sess:
                                # 1. Delete all CategoryMaps
                                db_sess.query(CategoryMap).delete()
                                
                                # 2. Reset category_id for transactions?
                                db_sess.query(Transaction).update({Transaction.category_id: None}, synchronize_session=False)
                                
                                db_sess.commit()
                                return True

                        await asyncio.to_thread(_clear_op)
                        # Check if n exists before dismissing
                        try: n.dismiss() 
                        except: pass
                        
                        ui.notify("All keyword associations cleared.", type='positive')
                        load_data()
                        clear_dialog.close()
                    except Exception as e:
                        try: n.dismiss()
                        except: pass
                        if clear_btn:
                            clear_btn.props(remove='loading')
                            clear_btn.enable()
                        ui.notify(f"Error: {e}", type='negative')

                clear_dialog = ui.dialog()
                with clear_dialog, ui.card():
                    ui.label("WARNING: Clear All Associations?").classes('text-lg font-bold text-red-600')
                    ui.label("This will delete ALL keyword rules and unassign categories from transactions.").classes('mb-4')
                    with ui.row().classes('justify-end'):
                        ui.button('Cancel', on_click=clear_dialog.close).props('flat')
                        clear_btn = ui.button('Clear All', on_click=do_clear).classes('bg-red-600 text-white')
                clear_dialog.open()

            async def handle_download_csv():
                # Get current rules
                grid_params = {'fileName': 'keyword_mappings.csv'}
                try:
                    res = await grid.run_grid_method('exportDataAsCsv', grid_params)
                except Exception:
                     # Ignore client side disconnection error if download triggers nav
                    pass

            with ui.row().classes('gap-4 mt-2'):
                ui.button('Edit Selected', on_click=handle_batch_edit).props('outline')
                with ui.row().classes('ml-auto gap-2'):
                     ui.button('Download CSV', on_click=handle_download_csv).props('flat icon=download')
                     ui.button('Clear All', on_click=handle_clear_all).classes('bg-red-100 text-red-800').props('flat icon=delete')
            
            ui.label('Changes in the dialog are saved immediately to the database.').classes('text-xs text-gray-400 mt-2')

    load_data()
