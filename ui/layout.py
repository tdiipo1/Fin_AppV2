from nicegui import ui

def frame(active_tab: str, content_func):
    """
    Standard App Shell with Navigation.
    """
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
        
        with ui.row().classes('gap-6'):
            nav_link('Dashboard', '/', 'dashboard', active_tab == 'dashboard')
            nav_link('Transactions', '/transactions', 'receipt_long', active_tab == 'transactions')
            nav_link('Import', '/import', 'upload_file', active_tab == 'import')
            nav_link('Settings', '/settings', 'settings', active_tab == 'settings')

    with ui.column().classes('w-full max-w-7xl mx-auto p-6 bg-slate-50 min-h-screen'):
        content_func()
