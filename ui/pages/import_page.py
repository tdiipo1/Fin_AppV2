from nicegui import ui
from services.importer import import_csv_transactions
from database.connection import get_db
import os

def content():
    ui.label('Import Data').classes('text-3xl font-bold text-slate-800 mb-6')
    
    with ui.card().classes('w-full max-w-2xl p-6'):
        ui.label('Upload Bank CSV').classes('text-xl font-bold mb-2')
        ui.label('Upload exports from Chase, Wells Fargo, SoFi, etc. Duplicate transactions will be automatically skipped based on fingerprinting.').classes('text-gray-500 mb-4 text-sm')
        
        log_area = ui.log().classes('w-full h-40 bg-slate-100 rounded p-2 mb-4')
        
        async def handle_upload(e):
            log_area.push(f"Received file: {e.name}")
            # Save to temp
            temp_path = f"dataset_upload_{e.name}"
            with open(temp_path, 'wb') as f:
                f.write(e.content.read())
            
            # Run Importer
            try:
                db = next(get_db())
                log_area.push("Analyzing schema...")
                added, skipped = import_csv_transactions(db, temp_path)
                log_area.push(f"✅ COMPLETE: Added {added} new transactions. Skipped {skipped} duplicates.")
                ui.notify(f"Imported {added} transactions!", type='positive')
            except Exception as err:
                log_area.push(f"❌ ERROR: {err}")
                ui.notify("Import failed", type='negative')
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        ui.upload(on_upload=handle_upload, auto_upload=True).classes('w-full').props('accept=.csv')
