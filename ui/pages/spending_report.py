from nicegui import ui
from datetime import datetime
from services.analytics import get_budget_comparison
from database.connection import get_db, SessionLocal
import pandas as pd

def spending_report_page():
    
    # State
    class ReportState:
        def __init__(self):
            now = datetime.now()
            self.year = now.year
            self.month = now.month
            self.data = [] # List of dicts
            
    s = ReportState()
    
    def load_data():
        start_date = datetime(s.year, s.month, 1)
        if s.month == 12:
            end_date = datetime(s.year + 1, 1, 1)
        else:
            end_date = datetime(s.year, s.month + 1, 1)
            
        with SessionLocal() as db:
            s.data = get_budget_comparison(db, start_date, end_date)
            
    load_data()
    
    # --- Renders ---
    
    @ui.refreshable
    def render_charts():
        if not s.data:
            ui.label("No data for this period.").classes('w-full text-center text-gray-500')
            return
            
        # Prepare Data
        # Group by Section for cleaner charts
        section_data = {} # {section: {budget: X, actual: Y}}
        for row in s.data:
            sec = row['section']
            if sec not in section_data:
                section_data[sec] = {'budget': 0, 'actual': 0}
            section_data[sec]['budget'] += row['budgeted']
            section_data[sec]['actual'] += row['actual']
            
        sections = sorted(section_data.keys())
        budgets = [round(section_data[k]['budget'], 2) for k in sections]
        actuals = [round(section_data[k]['actual'], 2) for k in sections]
        
        # 1. Budget vs Actual Bar Chart
        ui.echart({
            'title': {'text': 'Budget vs Actual by Section'},
            'tooltip': {'trigger': 'axis'},
            'legend': {'data': ['Budget', 'Actual']},
            'grid': {'left': '3%', 'right': '4%', 'bottom': '3%', 'containLabel': True},
            'xAxis': {'type': 'category', 'data': sections, 'axisLabel': {'rotate': 45}},
            'yAxis': {'type': 'value'},
            'series': [
                {'name': 'Budget', 'type': 'bar', 'data': budgets},
                {'name': 'Actual', 'type': 'bar', 'data': actuals}
            ]
        }).classes('w-full h-96')
        
    @ui.refreshable
    def render_table():
        if not s.data: return
        
        # AgGrid
        # Columns: Section, Category, Budgeted, Actual, Variance, Status
        
        cols = [
            {'headerName': 'Section', 'field': 'section', 'filter': True, 'sortable': True},
            {'headerName': 'Category', 'field': 'category', 'filter': True, 'sortable': True},
            {'headerName': 'Budgeted', 'field': 'budgeted', 'sortable': True, 'valueFormatter': "x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})"},
            {'headerName': 'Actual', 'field': 'actual', 'sortable': True, 'valueFormatter': "x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})"},
            {'headerName': 'Variance', 'field': 'variance', 'sortable': True, 
             'valueFormatter': "x.toLocaleString('en-US', {style: 'currency', currency: 'USD'})",
             'cellStyle': {'color': 'params.value < 0 ? "red" : "green"'}
            },
            {'headerName': 'Status', 'field': 'status', 'sortable': True, 
             'cellClassRules': {
                 'text-red-600 font-bold': 'x == "Over Budget"',
                 'text-green-600 font-bold': 'x == "Under Budget"',
             }
            },
        ]
        
        ui.aggrid({
            'columnDefs': cols,
            'rowData': s.data,
            'defaultColDef': {'flex': 1},
            'pagination': True,
            'paginationPageSize': 20
        }).classes('w-full h-96')
        
        # Calculation for summary
        total_budget = sum(d['budgeted'] for d in s.data)
        total_spent = sum(d['actual'] for d in s.data)
        total_var = total_budget - total_spent
        
        with ui.row().classes('w-full justify-end mt-4 gap-8'):
            with ui.column().classes('items-end'):
                ui.label('Total Budgeted').classes('text-sm text-gray-500')
                ui.label(f"${total_budget:,.2f}").classes('text-xl font-bold')
            with ui.column().classes('items-end'):
                ui.label('Total Spent').classes('text-sm text-gray-500')
                ui.label(f"${total_spent:,.2f}").classes('text-xl font-bold')
            with ui.column().classes('items-end'):
                ui.label('Net Variance').classes('text-sm text-gray-500')
                color = 'text-green-600' if total_var >= 0 else 'text-red-600'
                ui.label(f"${total_var:,.2f}").classes(f'text-xl font-bold {color}')
        
    def handle_date_change():
        load_data()
        render_charts.refresh()
        render_table.refresh()
    
    # --- Layout ---
    with ui.column().classes('w-full max-w-6xl mx-auto p-4'):
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label("Spending Report").classes('text-2xl font-bold')
            
            with ui.row().classes('items-center gap-2'):
                ui.label("Month:")
                ui.select(options=list(range(1, 13)), value=s.month, on_change=lambda e: setattr(s, 'month', e.value) or handle_date_change()).classes('w-20')
                ui.select(options=[2024, 2025, 2026], value=s.year, on_change=lambda e: setattr(s, 'year', e.value) or handle_date_change()).classes('w-24')

        render_charts()
        ui.separator().classes('my-6')
        render_table()
