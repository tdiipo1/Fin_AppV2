from nicegui import ui
from ui.state import filter_sidebar

def frame(active_tab: str, content_func):
    """
    Standard App Shell with Navigation.
    """
    # Initialize Filter Sidebar only for relevant tabs
    if active_tab in ['dashboard', 'intelligence']:
        filter_sidebar()

    with ui.header().classes('bg-slate-900 text-white items-center h-16 px-4 shadow-md'):
        ui.icon('savings', size='32px').classes('mr-2')
        ui.label('FinApp V2').classes('text-xl font-bold tracking-tight')
        
        ui.space()
        
        # Navigation Links
        def nav_link(label, target, icon_name, is_active):
            color = 'text-blue-400' if is_active else 'text-gray-300 hover:text-white'
            with ui.link(target=target).classes('no-underline'):
                with ui.row().classes('items-center gap-1'):
                    ui.icon(icon_name).classes(f'{color}')
                    ui.label(label).classes(f'{color} font-medium')
        
        with ui.row().classes('gap-6 items-center'):
            nav_link('Dashboard', '/', 'dashboard', active_tab == 'dashboard')
            nav_link('Analytics', '/intelligence', 'insights', active_tab == 'intelligence')
            nav_link('Transactions', '/transactions', 'receipt_long', active_tab == 'transactions')
            nav_link('Budget', '/budget', 'account_balance_wallet', active_tab == 'budget')
            nav_link('Spending', '/spending', 'pie_chart', active_tab == 'spending')
            nav_link('Import', '/import', 'upload_file', active_tab == 'import')
            nav_link('Mappings', '/mappings', 'map', active_tab == 'mappings')
            nav_link('Exclusions', '/excluded', 'visibility_off', active_tab in ['excluded', 'batch_exclude'])
            
            # Dark Mode Toggle (Beta)
            dm = ui.dark_mode()
            ui.switch('Dark Mode', on_change=dm.toggle).props('color=blue-400 keep-color')

    with ui.column().classes('w-full max-w-7xl mx-auto p-6 bg-slate-50 min-h-screen'):
        content_func()
