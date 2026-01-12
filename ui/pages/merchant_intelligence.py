from nicegui import ui
from database.connection import get_db
from services.merchant_analytics import get_top_entities, get_entity_time_series, get_entity_transactions
from datetime import date, timedelta
import pandas as pd
import plotly.graph_objects as go
from ui.state import app_state

def content():
    ui.label('Analytics & Intelligence').classes('text-3xl font-bold text-slate-800 mb-6')
    
    db = next(get_db())
    
    # --- Deep Dive Modal ---
    deep_dive_dialog = ui.dialog().classes('w-full')
    
    def show_deep_dive(entity_name, entity_type):
        deep_dive_dialog.clear()
        
        # Fetch Data
        txns = get_entity_transactions(db, entity_name, entity_type, app_state.start_date, app_state.end_date)
        trend = get_entity_time_series(db, entity_name, entity_type, app_state.start_date, app_state.end_date, group_by='month')
        
        # Calcs
        total_spent = sum(t['amount'] for t in txns) # Amounts are negative
        total_abs = abs(total_spent)
        count = len(txns)
        avg = total_abs / count if count > 0 else 0
        
        with deep_dive_dialog, ui.card().classes('w-[90vw] max-w-6xl h-[85vh] flex flex-col'):
            # Header
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.label(f" {entity_name} ({entity_type})").classes('text-2xl font-bold')
                ui.button(icon='close', on_click=deep_dive_dialog.close).props('flat round')
            
            # Metrics
            with ui.row().classes('w-full gap-4 mb-6'):
                with ui.card().classes('p-4 bg-red-50'):
                    ui.label('Total Spent').classes('text-xs text-gray-500 uppercase')
                    ui.label(f"${total_abs:,.2f}").classes('text-xl font-bold text-red-700')
                with ui.card().classes('p-4'):
                    ui.label('Transactions').classes('text-xs text-gray-500 uppercase')
                    ui.label(str(count)).classes('text-xl font-bold')
                with ui.card().classes('p-4'):
                    ui.label('Avg Ticket').classes('text-xs text-gray-500 uppercase')
                    ui.label(f"${avg:,.2f}").classes('text-xl font-bold')
            
            # Chart & Grid
            # Use Splitter for resilient layout
            with ui.splitter(value=60).classes('w-full flex-grow border rounded') as splitter:
                with splitter.before:
                    with ui.column().classes('w-full h-full p-2'):
                        if trend:
                            fig = go.Figure()
                            dates = [t['date'] for t in trend]
                            amounts = [abs(t['amount']) for t in trend]
                            fig.add_trace(go.Scatter(x=dates, y=amounts, mode='lines+markers', name='Spend', line=dict(color='#3b82f6')))
                            fig.update_layout(
                                title="Spending Trend (Monthly)", 
                                margin=dict(l=20, r=20, t=40, b=20),
                                template="plotly_white",
                                xaxis_title="Date",
                                yaxis_title="Amount ($)"
                            )
                            ui.plotly(fig).classes('w-full h-full')
                        else:
                            ui.label('No trend data available for this selection.').classes('text-gray-400 italic p-4')

                with splitter.after:
                     with ui.column().classes('w-full h-full bg-slate-50 p-2 overflow-hidden'):
                         ui.label('Recent Transactions').classes('font-bold mb-2')
                         
                         if txns:
                             ui.aggrid({
                                 'columnDefs': [
                                     {'field': 'date', 'width': 100},
                                     {'field': 'amount', 'width': 90, 'valueFormatter': "value.toFixed(2)"},
                                     {'field': 'source', 'width': 120},
                                     {'field': 'raw_description', 'headerName': 'Desc', 'width': 150}
                                 ],
                                 'rowData': txns,
                                 'defaultColDef': {'sortable': True, 'resizable': True},
                                 'domLayout': 'normal', # Scrollable within container
                             }).classes('w-full h-full')
                         else:
                             ui.label('No transactions found').classes('text-gray-400 italic')

        deep_dive_dialog.open()

    
    # Main Container for Dynamic Content
    view_container = ui.column().classes('w-full')

    # --- Filter Bar (Deprecated in favor of Sidebar, but keeping refresh logic) ---
    def refresh_view():
        view_container.clear()
        
        # Use Shared State
        # Determine grouping
        group_mode = app_state.aggregation_level or 'Merchant'
        
        top_data = get_top_entities(
            db, 
            app_state.start_date, 
            app_state.end_date, 
            limit=app_state.top_n_merchants,
            group_by=group_mode
        )
        
        with view_container:
            ui.label(f"Top {app_state.top_n_merchants} {group_mode}s ({app_state.start_date} to {app_state.end_date})").classes('text-xl font-bold mb-4')
            
            # --- Visualizations ---
            with ui.row().classes('w-full h-80 mb-6'):
                if top_data:
                     fig = go.Figure(data=[
                         go.Bar(
                             x=[m['standardized_merchant'] for m in top_data], # Key reused as 'entity_name'
                             y=[m['total_amount'] for m in top_data],
                             marker_color='indianred'
                         )
                     ])
                     fig.update_layout(
                         title=f'Top {group_mode}s by Spend',
                         margin=dict(l=20, r=20, t=30, b=50)
                     )
                     ui.plotly(fig).classes('w-full h-full')

            # --- Data Table ---
            # Dynamic Columns based on group_mode
            entity_header = group_mode
            
            grid = ui.aggrid({
                'columnDefs': [
                    {'headerName': entity_header, 'field': 'standardized_merchant', 'width': 250, 'filter': True, 'pinned': 'left'},
                    {'headerName': 'Total Spent', 'field': 'total_amount', 'width': 130, 
                     'valueFormatter': "value.toLocaleString('en-US', {style: 'currency', currency: 'USD'})", 'sort': 'desc'},
                    {'headerName': 'Count', 'field': 'transaction_count', 'width': 100},
                    {'headerName': 'Avg', 'field': 'avg_transaction', 'width': 100, 
                     'valueFormatter': "value.toLocaleString('en-US', {style: 'currency', currency: 'USD'})"}
                ],
                'rowData': top_data,
                'defaultColDef': {'sortable': True, 'resizable': True},
                'rowSelection': 'single',
                'pagination': True,
                'paginationPageSize': 20
            }).classes('w-full h-96')
            
            # Event Handler
            async def on_row_click(e):
                if e.args['data']:
                    entity = e.args['data']['standardized_merchant']
                    type_ = e.args['data']['entity_type']
                    show_deep_dive(entity, type_)
            
            grid.on('cellClicked', on_row_click)
            
            ui.label('Click on a row to see details.').classes('text-sm text-gray-400 mt-2')

    # Register refresh callback to shared state
    app_state.register_callback(refresh_view)

    # Initial Load
    refresh_view()
