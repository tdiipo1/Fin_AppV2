from nicegui import ui
from services.importer import import_csv_transactions
from services.ai import run_auto_categorization
from database.connection import get_db
import os
import shutil

# Ensure uploads directory exists
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'uploads') 
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

def content():
    ui.label('Import Data').classes('text-3xl font-bold text-slate-800 mb-6')
    
    # State to track staged files
    staged_files = []
    
    def refresh_file_list():
        file_list_container.clear()
        with file_list_container:
            if not staged_files:
                ui.label('No files staged for import.').classes('text-gray-500 italic')
            else:
                for f in staged_files:
                    with ui.row().classes('items-center gap-2 w-full'):
                        ui.icon('description', size='sm').classes('text-blue-500')
                        ui.label(os.path.basename(f)).classes('font-medium flex-grow')
                        
                        # Delete button
                        def delete_handler(filepath=f):
                            if filepath in staged_files:
                                staged_files.remove(filepath)
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            refresh_file_list()
                            check_process_btn()
                            
                        ui.button(icon='delete', on_click=delete_handler).props('flat dense color=red round size=sm')

    def check_process_btn():
        if staged_files:
            process_btn.enable()
        else:
            process_btn.disable()

    async def handle_upload(e):
        try:
            # Based on debug output: e.file holds the data, and it has a 'name' attribute
            upload_obj = e.file
            filename = getattr(upload_obj, 'name', None)

            if not filename:
                 ui.notify("Upload failed: No filename found.", type='negative')
                 log_area.push(f"DEBUG Error: e.file missing name. Dir: {dir(upload_obj)}")
                 return

            log_area.push(f"Staging file: {filename}")
            filepath = os.path.join(UPLOAD_DIR, filename)
            
            # Read content from the upload object
            content = upload_obj.read()
            
            # Check if it's a coroutine (async read) and await it if so
            from inspect import iscoroutine
            if iscoroutine(content):
                content = await content
            
            # Write key file to disk
            with open(filepath, 'wb') as f:
                if isinstance(content, str):
                    f.write(content.encode('utf-8'))
                else:
                    f.write(content)

            if filepath not in staged_files:
                staged_files.append(filepath)
            
            refresh_file_list()
            check_process_btn()
            ui.notify(f"Staged {filename}", type='positive')
            
        except Exception as err:
            log_area.push(f"Error handling file: {err}")
            print(f"Error: {err}")

    async def process_imports():
        if not staged_files: return
        
        log_area.push("Starting import process...")
        db = next(get_db())
        
        process_btn.disable()
        spinner.visible = True
        
        batch_stats = {'added': 0, 'existing': 0, 'skipped': 0, 'errors': 0}

        try:
            # Iterate over a copy
            for filepath in list(staged_files):
                filename = os.path.basename(filepath)
                try:
                    log_area.push(f"--- Processing {filename} ---")
                    
                    # Call importer with filename as source
                    stats = import_csv_transactions(db, filepath, source_label=filename)
                    
                    # Update aggregate stats
                    batch_stats['added'] += stats.get('added', 0)
                    batch_stats['existing'] += stats.get('existing', 0)
                    batch_stats['skipped'] += stats.get('skipped', 0)
                    batch_stats['errors'] += stats.get('errors', 0)
                    
                    # Detailed File Log
                    log_area.push(f"  • Total Rows Found: {stats.get('total_rows', 0)}")
                    log_area.push(f"  • New Imported: {stats.get('added', 0)}")
                    log_area.push(f"  • Already in DB: {stats.get('existing', 0)}")
                    
                    skipped_count = stats.get('skipped', 0) - stats.get('existing', 0)
                    if skipped_count > 0:
                         log_area.push(f"  • Skipped (Other): {skipped_count}")

                    # Log Skipped Details
                    if stats.get('skipped_details'):
                        for reason in stats['skipped_details']:
                            log_area.push(f"    ⚠️ SKIPPED: {reason}")

                    # Log Errors
                    if stats.get('error_details'):
                        for err in stats['error_details']:
                            log_area.push(f"    ❌ ERROR: {err}")
                    
                    log_area.push("-----------------------------------")

                    # Remove file after successful processing
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    
                except Exception as err:
                    log_area.push(f"❌ Critical Error processing {filename}: {err}")
            
            staged_files.clear()
            refresh_file_list()
            
            summary_msg = f"Batch Complete! Added: {batch_stats['added']}, Existing: {batch_stats['existing']}"
            ui.notify(summary_msg, type='positive')
            log_area.push(f"✅ {summary_msg}")

        except Exception as e:
            ui.notify(f"Critical Error: {e}", type='negative')
            log_area.push(f"❌ CRITICAL ERROR: {e}")
        finally:
            spinner.visible = False
            check_process_btn()


    async def run_ai_categorization():
        try:
            ai_btn.disable()
            ai_spinner.visible = True
            log_area.push("🤖 Starting AI Categorization...")
            log_area.push("Connecting to Gemini...")
            
            # Run in executor to avoid blocking UI
            import asyncio
            db = next(get_db())
            loop = asyncio.get_event_loop()
            
            # Wrapping DB op in thread if needed, but since it's IO heavy on API call, thread is good.
            # services.ai.run_auto_categorization is synchronous.
            processed_count, rules_count = await loop.run_in_executor(None, run_auto_categorization, db)
            
            msg = f"✅ AI Complete. Categorized {processed_count} transactions. Learned {rules_count} new rules."
            log_area.push(msg)
            ui.notify(msg, type='positive')
            
        except Exception as e:
            err_msg = f"❌ AI Error: {e}"
            log_area.push(err_msg)
            ui.notify("AI Categorization Failed", type='negative')
            print(e)
        finally:
            ai_spinner.visible = False
            ai_btn.enable()

    def handle_rejected(e):
        ui.notify(f"Rejected {e.entries[0]['name']}. Please ensure it is a valid CSV file.", type='negative')

    with ui.card().classes('w-full max-w-4xl p-6'):
        ui.label('1. Upload CSV Files').classes('text-xl font-bold mb-2')
        ui.label('Upload exports from your banks.').classes('text-gray-500 mb-4 text-sm')
        
        # Nicer upload area
        ui.upload(on_upload=handle_upload, on_rejected=handle_rejected, multiple=True, auto_upload=True).classes('w-full').props('accept=".csv, .CSV" label="Drop CSV files here"')
        
        ui.separator().classes('my-6')
        
        ui.label('2. Staged Files').classes('text-xl font-bold mb-2')
        file_list_container = ui.column().classes('w-full mb-4 pl-4 border-l-2 border-slate-200 bg-slate-50 p-2 rounded')
        refresh_file_list()

        ui.separator().classes('my-6')

        with ui.row().classes('items-center gap-4'):
            process_btn = ui.button('Process Import', on_click=process_imports).classes('bg-blue-600 text-white shadow-md')
            process_btn.disable()
            spinner = ui.spinner(size='lg').classes('text-blue-600')
            spinner.visible = False
            
            ui.space()
            
            # AI Button
            with ui.row().classes('items-center'):
                ai_btn = ui.button('Auto-Categorize with AI', on_click=run_ai_categorization, icon='auto_awesome').classes('bg-purple-600 text-white shadow-md')
                ai_spinner = ui.spinner(size='md').classes('text-purple-600')
                ai_spinner.visible = False
        
        ui.separator().classes('my-6')
        
        ui.label('Import Log').classes('font-bold text-gray-700')
        log_area = ui.log().classes('w-full h-48 bg-slate-900 text-green-400 rounded p-2 font-mono text-xs shadow-inner')
