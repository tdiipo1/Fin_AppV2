from nicegui import ui
from database.connection import get_db
from database.models import Transaction

def content():
    ui.label('All Transactions').classes('text-3xl font-bold text-slate-800 mb-6')
    
    db = next(get_db())
    # Limit to 100 for now to avoid hanging browser if large DB
    txs = db.query(Transaction).order_by(Transaction.date.desc()).limit(200).all()
    
    rows = []
    for t in txs:
        rows.append({
            'date': t.date.strftime('%Y-%m-%d'),
            'description': t.description,
            'amount': t.amount,
            'account': t.account_name,
            'source': t.import_method
        })
    
    # AG Grid
    ui.aggrid({
        'columnDefs': [
            {'headerName': 'Date', 'field': 'date', 'sortable': True, 'filter': True},
            {'headerName': 'Description', 'field': 'description', 'sortable': True, 'filter': True, 'flex': 2},
            {
                'headerName': 'Amount', 
                'field': 'amount', 
                'sortable': True, 
                'filter': 'agNumberColumnFilter',
                'valueFormatter': "x.value.toLocaleString('en-US', {style: 'currency', currency: 'USD'})",
                'cellClassRules': {
                    'text-green-600 font-bold': 'x > 0',
                    'text-red-500': 'x < 0'
                }
            },
            {'headerName': 'Account', 'field': 'account', 'sortable': True, 'filter': True},
            {'headerName': 'Source', 'field': 'source', 'sortable': True, 'filter': True},
        ],
        'rowData': rows,
        'pagination': True,
        'paginationPageSize': 20
    }).classes('h-screen w-full shadow-sm rounded-lg')
