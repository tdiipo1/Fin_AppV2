from nicegui import ui
from database.connection import get_db
from database.models import ExclusionRule
import os
import pandas as pd
import asyncio

# Ensure uploads directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'uploads')
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

def content():
    ui.label('Batch Import Exclusions').classes('text-3xl font-bold text-slate-800 mb-6')

    # State
    state = {
        'staged_file': None,
        'filename': None
    }
    
    # Container for results (defined early so we can clear it)
    results_container = ui.column().classes('w-full mt-6')
    
    # UI Elements (forward declared for handlers)
    status_label = ui.label('No file staged.').classes('text-gray-500 italic mb-4 block')
    process_btn = ui.button('Process Import', icon='play_arrow').props('disabled color=green')

    # --- Handlers ---

    async def download_template():
        # Create a sample CSV with appropriate headers
        content = (
            "rule_type,value,is_active\n"
            "contains,Example Keyword,1\n"
            "regex,^Start.*End$,1\n"
            "exact_match,Exact Description Text,1"
        )
        ui.download(content.encode('utf-8'), 'exclusion_template.csv')

    async def handle_upload(e):
        try:
            upload_obj = e.file
            filename = getattr(upload_obj, 'name', 'upload.csv')
            filepath = os.path.join(UPLOAD_DIR, filename)
            
            # Read and Save
            content = upload_obj.read()
            from inspect import iscoroutine
            if iscoroutine(content):
                content = await content
                
            with open(filepath, 'wb') as f:
                if isinstance(content, str):
                    f.write(content.encode('utf-8'))
                else:
                    f.write(content)
            
            # Update State
            state['staged_file'] = filepath
            state['filename'] = filename
            
            # Update UI
            status_label.text = f"File ready: {filename}"
            status_label.classes(remove='text-gray-500 italic', add='text-blue-600 font-bold')
            process_btn.enable()
            process_btn.props(remove='disabled')
            
            # Clear previous results
            results_container.clear()
            ui.notify('File uploaded successfully. Click Process to start.', type='positive')
            
        except Exception as ex:
            ui.notify(f"Upload failed: {ex}", type='negative')

    async def run_import():
        if not state['staged_file']:
            return

        process_btn.props('loading')
        process_btn.disable()
        results_container.clear()
        
        try:
            db = next(get_db())
            filepath = state['staged_file']
            
            # Read CSV
            try:
                # Try reading with default settings first
                df = pd.read_csv(filepath)
            except Exception as e:
                # Fallback to simple line reading if CSV parsing fails heavily (unlikely with pandas)
                ui.notify(f"Failed to read CSV: {e}", type='negative')
                process_btn.props(remove='loading')
                return

            # Normalize headers
            df.columns = [c.strip().lower() for c in df.columns]
            
            records = []
            
            # Determine column mapping
            has_value_col = 'value' in df.columns
            
            seen_in_batch = set()

            for _, row in df.iterrows():
                # Extract Data
                if has_value_col:
                    val = str(row.get('value', '')).strip()
                    rtype = str(row.get('rule_type', 'contains')).strip()
                    active_val = str(row.get('is_active', '1')).strip()
                    is_active = active_val in ['1', 'true', 'True', 'yes']
                else:
                    # Single column fallback - assume the first column is the value
                    val = str(row.iloc[0]).strip()
                    # Heuristic for rule type
                    is_regex = any(c in val for c in ['^', '$', '.*', '[', '(', '|'])
                    rtype = 'regex' if is_regex else 'contains'
                    is_active = True

                # Validation
                if not val or val.lower() == 'nan':
                    continue
                
                # Check for duplicate in current batch
                if val in seen_in_batch:
                    records.append({
                        'value': val,
                        'type': rtype,
                        'active': is_active,
                        'status': "Skipped (Duplicate in File)",
                        '_result': "skipped"
                    })
                    continue

                # Check for Duplicates in DB
                exists = db.query(ExclusionRule).filter(ExclusionRule.value == val).first()
                
                status_msg = "Skipped"
                result_type = "skipped" # for logic/coloring
                
                if not exists:
                    # Validate rule_type
                    if rtype not in ['exact_match', 'regex', 'contains']:
                        rtype = 'contains' 
                        
                    new_rule = ExclusionRule(rule_type=rtype, value=val, is_active=is_active)
                    db.add(new_rule)
                    seen_in_batch.add(val) # Track as added
                    status_msg = "Imported"
                    result_type = "imported"
                else:
                    status_msg = f"Skipped (Exists: ID {exists.id})"
                
                records.append({
                    'value': val,
                    'type': rtype,
                    'active': is_active,
                    'status': status_msg,
                    '_result': result_type
                })
            
            db.commit()
            
            # Stats
            imported_count = sum(1 for r in records if r['_result'] == 'imported')
            skipped_count = len(records) - imported_count
            
            ui.notify(f"Process Complete: {imported_count} imported, {skipped_count} skipped.", type='positive')
            
            # Render Results Grid
            with results_container:
                ui.label(f"Import Summary: {imported_count} Added, {skipped_count} Skipped").classes('text-xl font-bold mb-2')
                
                if records:
                    ui.aggrid({
                        'defaultColDef': {'sortable': True, 'filter': True, 'resizable': True, 'suppressHeaderMenuButton': True},
                        'columnDefs': [
                            {'headerName': 'Status', 'field': 'status', 'width': 250}, 
                            {'headerName': 'Rule Type', 'field': 'type', 'width': 150},
                            {'headerName': 'Value / Pattern', 'field': 'value', 'width': 400},
                            {'headerName': 'Active', 'field': 'active', 'width': 100}
                        ],
                        'rowData': records,
                        'pagination': True,
                        'paginationPageSize': 50,
                    }).classes('w-full h-96')
                else:
                    ui.label('No records to display.').classes('text-gray-400 italic')
                
        except Exception as e:
            ui.notify(f"Processing Error: {e}", type='negative')
            print(f"Error: {e}")
        finally:
            process_btn.props(remove='loading')
            # Clean up file
            if state['staged_file'] and os.path.exists(state['staged_file']):
                try:
                    os.remove(state['staged_file'])
                except: pass
            
            # Reset UI state partially
            state['staged_file'] = None
            status_label.text = "File processed."
            status_label.classes(remove='text-blue-600 font-bold', add='text-gray-500 italic')


    # --- Layout Construction ---
    
    with ui.row().classes('w-full gap-6 items-start'):
        
        # Left: Upload
        with ui.card().classes('flex-1 p-6'):
            with ui.row().classes('justify-between items-center w-full mb-4'):
                ui.label('Step 1: Upload File').classes('text-xl font-bold')
                ui.button('Download Template', icon='download', on_click=download_template).props('flat dense size=sm')

            ui.markdown("""
            Upload a **CSV** file containing your exclusion keywords.
            
            **Auto-Mapping:**
            - If header `rule_type`, `value`, `is_active` exists: Uses those columns.
            - If no headers/other headers: Assumes 1st column is `value` and guesses type (`regex` if special chars found, else `contains`).
            """)
            
            ui.upload(on_upload=handle_upload, auto_upload=True).props('accept=".csv, .txt" label="Select or Drop File"').classes('w-full')

        # Right: Process
        with ui.card().classes('flex-1 p-6') as process_card:
            ui.label('Step 2: Process').classes('text-xl font-bold mb-4')
            
            # Status display
            status_label.move(process_card)
            
            ui.separator().classes('my-4')
            
            # Button
            process_btn.on('click', run_import)
            process_btn.move(process_card)
            
    # Results Area below
    results_container

