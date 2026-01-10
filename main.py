from nicegui import ui
import os
from database.connection import init_db
from services.backup import perform_daily_backup
from ui.layout import frame
from ui.pages import dashboard, transactions, import_page

# --- BACKUP SYSTEM ---
# Run daily backup on startup to ensure data is safe locally
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'finapp_v2.db')
BACKUP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backups')
perform_daily_backup(DB_PATH, BACKUP_PATH)

# Ensure DB tables exist
init_db()

# --- ROUTES ---

@ui.page('/')
def home():
    frame('dashboard', dashboard.content)

@ui.page('/transactions')
def trans_page():
    frame('transactions', transactions.content)

@ui.page('/import')
def imp_page():
    frame('import', import_page.content)

@ui.page('/settings')
def settings_page():
    def content():
        ui.label('Settings').classes('text-3xl font-bold')
        ui.label('Coming Soon: SimpleFin API Key Management, Gemini AI Config').classes('text-gray-500 mt-4')
    frame('settings', content)

# Start App
ui.run(title="FinApp V2", favicon="💸", dark=False, port=8081)
