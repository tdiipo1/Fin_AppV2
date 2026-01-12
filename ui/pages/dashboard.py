from nicegui import ui
from database.connection import get_db
from services.analytics import get_net_income_range, get_category_breakdown, get_budget_progress, get_monthly_transactions
from datetime import date, datetime
import plotly.graph_objects as go
from ui.state import app_state

def content():
    ui.label('Dashboard').classes('text-3xl font-bold text-slate-800 mb-6')
    
    db = next(get_db()) # Get DB session
    
    # --- Drill Down Dialog ---
    drill_down_dialog = ui.dialog().classes('w-full')
    
    def show_transactions(year, month, initial_type):
        drill_down_dialog.clear()
        
        month_name = date(year, month, 1).strftime('%B %Y')
        
        # We need to define the container variable first so load_grid can reference it
        # But we will assign the actual UI element inside the dialog context
        content_container = None 

        def load_grid(selected_type):
            if not content_container: return
            
            content_container.clear()
            
            # Map selection to service parameter
            service_type = selected_type
            if selected_type == 'All':
                 service_type = 'All' 
            
            txns = get_monthly_transactions(db, year, month, service_type, include_excluded=app_state.include_excluded)
            
            grid_data = []
            total_amt = 0
            for t in txns:
                grid_data.append({
                    'date': t.date.strftime('%Y-%m-%d'),
                    'description': t.description,
                    'category': t.category.category if t.category else 'Uncategorized',
                    'amount': t.amount
                })
                total_amt += t.amount
            
            # Determine display label
            # If Expense view, total_amt should be negative normally.
            # If "Total Spend", we usually display as positive number representing cost.
            # However, standard Accounting is: Income (+), Expense (-).
            display_total = total_amt
            
            with content_container:
                 # Summary Row
                 with ui.row().classes('w-full justify-between items-center mb-2'):
                     ui.label(f"{len(grid_data)} Transactions").classes('text-gray-500')
                     # Format: If standard accounting, just show value.
                     ui.label(f"Net Total: ${display_total:,.2f}").classes(
                         'text-xl font-bold ' + ('text-green-600' if total_amt > 0 else 'text-red-600')
                     )

                 if not grid_data:
                     ui.label('No transactions found.').classes('italic text-gray-500')
                 else:
                     # Important: domLayout='autoHeight' allows grid to fit content, but inside a scrollable container
                     # Or 'normal' with fixed height.
                     # Since we are in a flex-col with flex-grow, 'normal' is best, but we need to ensure the container has height.
                     ui.aggrid({
                         'columnDefs': [
                             {'field': 'date', 'headerName': 'Date', 'width': 110, 'sortable': True},
                             {'field': 'description', 'headerName': 'Description', 'width': 300, 'filter': True, 'resizable': True},
                             {'field': 'category', 'headerName': 'Category', 'width': 180, 'filter': True},
                             {'field': 'amount', 'headerName': 'Amount', 'width': 120, 'sortable': True, 
                              'valueFormatter': "value.toFixed(2)", 'type': 'numericColumn'}
                         ],
                         'rowData': grid_data,
                         'defaultColDef': {'sortable': True, 'resizable': True},
                         'domLayout': 'normal',
                     }).classes('w-full flex-grow')

        with drill_down_dialog, ui.card().classes('w-[90vw] max-w-5xl h-[80vh] flex flex-col'):
            # Header
            with ui.row().classes('w-full justify-between items-center mb-4'):
                with ui.row().classes('items-center gap-4'):
                    ui.label(f"{month_name}").classes('text-2xl font-bold')
                    ui.toggle(['Income', 'Expense', 'All'], value=initial_type, on_change=lambda e: load_grid(e.value)).props('no-caps')
                
                ui.button(icon='close', on_click=drill_down_dialog.close).props('flat round')
            
            # Create container directly in layout
            content_container = ui.column().classes('w-full flex-grow overflow-hidden')
            
            # Initial Load
            load_grid(initial_type)
        
        drill_down_dialog.open()

    # Clean container for dashboard content
    dashboard_container = ui.column().classes('w-full')

    def refresh_dashboard():
        dashboard_container.clear()
        
        # Use Shared State
        start = app_state.start_date
        end = app_state.end_date
        # Use global include_excluded from state
        show_excluded = app_state.include_excluded
        
        # Context: Focus Month = Month of End Date
        focus_year = end.year
        focus_month = end.month
        focus_month_name = date(focus_year, focus_month, 1).strftime('%B %Y')
        
        with dashboard_container:
            ui.label(f'Analysis Period: {start.strftime("%d %b %Y")} - {end.strftime("%d %b %Y")}').classes('text-gray-500 mb-2 font-medium')
            if show_excluded:
                ui.label('Showing Excluded Transactions').classes('text-xs text-orange-500 font-bold mb-2')

            # --- 1. Net Income Chart (Range) ---
            monthly_data = get_net_income_range(db, start, end, include_excluded=show_excluded)
            
            if monthly_data:
                months = [m[0] for m in monthly_data]
                incomes = [m[1] or 0 for m in monthly_data]
                expenses = [abs(m[2] or 0) for m in monthly_data]

                fig_bar = go.Figure(data=[
                    go.Bar(name='Income', x=months, y=incomes, marker_color='#22c55e'),
                    go.Bar(name='Expense', x=months, y=expenses, marker_color='#ef4444')
                ])
                fig_bar.update_layout(
                    barmode='group', 
                    title_text='Income vs Expense (Selected Range) - Click bars for details', 
                    height=350, 
                    margin=dict(l=20, r=20, t=40, b=20),
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)',
                    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                    hovermode="x unified"
                )
                
                def handle_chart_click(e):
                    if e.args and 'points' in e.args:
                        point = e.args['points'][0]
                        date_str = point['x']
                        
                        # Use curveNumber for reliability (Trace 0=Income, Trace 1=Expense)
                        curve_idx = point.get('curveNumber', 0)
                        trace_name = 'Expense' if curve_idx == 1 else 'Income'
                        
                        try:
                            parts = date_str.split('-')
                            if len(parts) >= 2:
                                year = int(parts[0])
                                month = int(parts[1])
                                show_transactions(year, month, trace_name)
                            else:
                                raise ValueError("Invalid date format")
                        except (ValueError, IndexError):
                            ui.notify(f"Could not parse date: {date_str}", type='negative')

                with ui.card().classes('w-full p-4 mb-6'):
                    chart = ui.plotly(fig_bar).classes('w-full h-80')
                    # Enable click events
                    chart.on('plotly_click', handle_chart_click)
            else:
                 with ui.card().classes('w-full p-4 mb-6'):
                     ui.label('No data available for the selected range.').classes('text-gray-400 italic')

            # --- 2. Focus Month Breakdown ---
            with ui.row().classes('w-full gap-6'):
                
                # Left: Budget Progress
                with ui.card().classes('flex-1 p-6'):
                    with ui.row().classes('justify-between w-full items-baseline mb-4'):
                        ui.label(f'Budget Progress').classes('text-xl font-bold')
                        ui.label(focus_month_name).classes('text-sm px-2 py-1 bg-blue-100 text-blue-800 rounded')
                    
                    budgets = get_budget_progress(db, focus_year, focus_month, include_excluded=show_excluded)
                    if not budgets:
                        ui.label('No budget data found.').classes('text-gray-400 italic')
                        ui.link('Create Budget?', '/settings').classes('text-blue-500 text-sm')
                    
                    for b in budgets:
                        with ui.column().classes('w-full mb-3'):
                            # Label Row
                            with ui.row().classes('w-full justify-between items-end mb-1'):
                                ui.label(b['section']).classes('font-medium text-slate-700')
                                ui.label(f' / ').classes('text-sm text-gray-500')
                            
                            # Progress Bar
                            budget_val = b['budget'] if b['budget'] > 0 else 1
                            spent_val = b['spent']
                            percent = min(spent_val / budget_val, 1.0)
                            color = 'ef4444' if spent_val > budget_val else '3b82f6' # red if over, blue if under
                            
                            ui.linear_progress(percent).props(f'size="10px" color="#{color}" track-color="gray-200" rounded')

                # Right: Sunburst Chart
                with ui.card().classes('flex-1 p-4'):
                    with ui.row().classes('justify-between w-full items-baseline mb-2'):
                         ui.label('Spending Breakdown').classes('text-xl font-bold')
                         ui.label(focus_month_name).classes('text-sm px-2 py-1 bg-yellow-100 text-yellow-800 rounded')

                    cat_data = get_category_breakdown(db, focus_year, focus_month, include_excluded=show_excluded)
                    
                    if not cat_data:
                        ui.label('No transaction data for chart.').classes('text-gray-400 italic')
                    else:
                        labels = [d['category'] for d in cat_data]
                        parents = [d['section'] for d in cat_data]
                        values = [d['amount'] for d in cat_data]
                        
                        # Add root nodes (Sections)
                        unique_sections = list(set(parents))
                        for s in unique_sections:
                            if s not in labels:
                                labels.append(s)
                                parents.append('') # Root
                                # Sum values for section
                                v = sum([d['amount'] for d in cat_data if d['section'] == s])
                                values.append(v)

                        fig_sun = go.Figure(go.Sunburst(
                            labels=labels,
                            parents=parents,
                            values=values,
                            branchvalues='total'
                        ))
                        fig_sun.update_layout(margin=dict(t=10, l=10, r=10, b=10))
                        ui.plotly(fig_sun).classes('w-full h-80')

    # Register for updates when filters change
    app_state.register_callback(refresh_dashboard)
    
    # Run once
    refresh_dashboard()
