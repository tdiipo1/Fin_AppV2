from nicegui import ui
from database.connection import get_db
from database.models import Transaction
from sqlalchemy import func

def content():
    db = next(get_db())
    
    # Quick Stats
    total_count = db.query(func.count(Transaction.id)).scalar()
    net_worth = db.query(func.sum(Transaction.amount)).scalar() or 0.0
    recent_tx = db.query(Transaction).order_by(Transaction.date.desc()).limit(5).all()
    
    ui.label('Dashboard').classes('text-3xl font-bold text-slate-800 mb-6')
    
    # KPI Cards
    with ui.row().classes('w-full gap-4 mb-8'):
        with ui.card().classes('flex-1 bg-white p-4 shadow-sm'):
            ui.label('Total Net Volume').classes('text-sm text-gray-500 uppercase font-semibold')
            color = 'text-green-600' if net_worth >= 0 else 'text-red-500'
            ui.label(f"${net_worth:,.2f}").classes(f'text-3xl font-bold {color}')
            
        with ui.card().classes('flex-1 bg-white p-4 shadow-sm'):
            ui.label('Total Transactions').classes('text-sm text-gray-500 uppercase font-semibold')
            ui.label(f"{total_count:,}").classes('text-3xl font-bold text-slate-800')

        with ui.card().classes('flex-1 bg-white p-4 shadow-sm'):
            ui.label('Data Source').classes('text-sm text-gray-500 uppercase font-semibold')
            ui.label('Local SQLite').classes('text-3xl font-bold text-blue-600')

    # Recent Activity
    ui.label('Recent Activity').classes('text-xl font-bold text-slate-700 mb-4')
    if not recent_tx:
        ui.label('No transactions found. Go to Import tab.').classes('text-gray-500 italic')
    else:
        with ui.card().classes('w-full p-0 shadow-sm'):
            # Simple List View
            for tx in recent_tx:
                with ui.row().classes('w-full items-center p-3 border-b border-gray-100 hover:bg-gray-50'):
                    # Date Box
                    with ui.column().classes('items-center justify-center bg-gray-100 rounded px-3 py-1 mr-4'):
                        ui.label(tx.date.strftime("%b")).classes('text-xs font-bold text-gray-500 uppercase')
                        ui.label(tx.date.strftime("%d")).classes('text-lg font-bold text-slate-800 leading-none')
                    
                    # Details
                    with ui.column().classes('flex-grow'):
                        ui.label(tx.description).classes('font-medium text-slate-800')
                        ui.label(tx.account_name or 'Unknown Source').classes('text-xs text-gray-400')
                    
                    # Amount
                    amt_cls = 'text-green-600' if tx.amount > 0 else 'text-slate-900'
                    ui.label(f"${tx.amount:,.2f}").classes(f'font-bold {amt_cls}')
