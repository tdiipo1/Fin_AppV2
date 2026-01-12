from nicegui import ui
from datetime import date, timedelta

class AppState:
    def __init__(self):
        self.start_date = date.today().replace(day=1) - timedelta(days=365)
        self.end_date = date.today()
        self.top_n_merchants = 20
        self.aggregation_level = 'Merchant' # Default
        self.include_excluded = False
        self.refresh_callbacks = []

    def register_callback(self, callback):
        self.refresh_callbacks.append(callback)

    def trigger_refresh(self):
        print("Triggering refresh for callbacks:", len(self.refresh_callbacks)) # Debug
        for callback in self.refresh_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"Error in callback: {e}")

# Global instance
app_state = AppState()

def filter_sidebar():
    with ui.right_drawer(value=True).classes('bg-slate-50 p-4 border-l') as drawer:
        ui.label('Filters').classes('text-xl font-bold mb-4')
        
        ui.label('Date Range').classes('text-sm font-bold text-gray-500 mt-2')
        start_input = ui.input('Start Date', value=app_state.start_date.isoformat()).props('type=date')
        end_input = ui.input('End Date', value=app_state.end_date.isoformat()).props('type=date')
        
        ui.label('Analysis Settings').classes('text-sm font-bold text-gray-500 mt-4')
        top_n_input = ui.number('Top Items count', value=app_state.top_n_merchants, min=5, max=100)
        
        agg_options = ['Merchant', 'Category', 'Subcategory', 'Section']
        agg_select = ui.select(agg_options, value=app_state.aggregation_level, label='Group By')
        
        ui.label('Data Visibility').classes('text-sm font-bold text-gray-500 mt-4')
        include_excluded_switch = ui.switch('Show Excluded', value=app_state.include_excluded)
        
        def apply_filters():
            try:
                app_state.start_date = date.fromisoformat(start_input.value)
                app_state.end_date = date.fromisoformat(end_input.value)
                app_state.top_n_merchants = int(top_n_input.value)
                app_state.aggregation_level = agg_select.value
                app_state.include_excluded = include_excluded_switch.value
                app_state.trigger_refresh()
                ui.notify('Filters applied', type='positive')
            except ValueError:
                ui.notify('Invalid date format', type='negative')

        ui.button('Apply Filters', on_click=apply_filters).classes('w-full mt-6 bg-blue-600')
        
    return drawer
