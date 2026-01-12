from nicegui import ui
from database.connection import get_db
from database.models import Transaction, ExclusionRule
from sqlalchemy import or_

def content():
    ui.label('Exclusion Management').classes('text-3xl font-bold text-slate-800 mb-6')
    
    db = next(get_db())

    # --- Section 1: Manage Rules ---
    with ui.card().classes('w-full p-4 mb-6'):
        ui.label('Exclusion Rules').classes('text-xl font-bold mb-2')
        ui.label('Transactions matching these rules will be hidden from analytics.').classes('text-sm text-gray-500 mb-4')
        
        # New Rule Form
        with ui.row().classes('items-end gap-2 mb-4 w-full'):
            new_rule_val = ui.input('Pattern / Value').props('dense outlined placeholder="e.g. transfer"').classes('flex-grow')
            new_rule_type = ui.select(['exact_match', 'regex', 'contains'], value='contains', label='Type').props('dense outlined').classes('w-40')
            
            async def add_rule():
                val = new_rule_val.value.strip()
                if not val: 
                    ui.notify('Please enter a value', type='warning')
                    return
                
                try:
                    exists = db.query(ExclusionRule).filter(ExclusionRule.value == val).first()
                    if exists:
                        ui.notify('Rule already exists', type='warning')
                        return
                        
                    new_rule = ExclusionRule(rule_type=new_rule_type.value, value=val, is_active=True)
                    db.add(new_rule)
                    db.commit()
                    new_rule_val.value = ''
                    refresh_rules()
                    ui.notify('Rule added successfully')
                except Exception as e:
                    ui.notify(f'Error: {e}', type='negative')

            ui.button(icon='add', on_click=add_rule).props('flat round color=blue')
        
        # Collapsible Rules List
        with ui.expansion('View All Rules', icon='list').props('dense').classes('w-full'):
            rules_container = ui.column().classes('w-full max-h-96 overflow-y-auto')

            def refresh_rules():
                rules_container.clear()
                rules = db.query(ExclusionRule).all()
                
                with rules_container:
                    if not rules:
                        ui.label("No exclusion rules defined.").classes('text-gray-400 italic p-2')
                    else:
                        ui.label(f'Total: {len(rules)} rules').classes('text-sm text-gray-600 mb-2 px-2')
                        for r in rules:
                            with ui.row().classes('items-center gap-4 w-full border-b p-2 hover:bg-gray-50'):
                                
                                # Toggle Active
                                async def toggle_active(rule_id=r.id, box=None):
                                    r_db = db.query(ExclusionRule).filter(ExclusionRule.id == rule_id).first()
                                    if r_db:
                                        r_db.is_active = not r_db.is_active
                                        db.commit()
                                        refresh_rules()
                                    
                                ui.checkbox(value=r.is_active, on_change=lambda e, rid=r.id: toggle_active(rid)).props('dense')
                                
                                ui.label(r.value).classes('font-mono text-sm flex-grow text-gray-800')
                                
                                ui.chip(r.rule_type, color='blue' if r.is_active else 'grey').props('dense outline size=sm')
                                
                                # Delete
                                async def delete_rule(rule_id=r.id): 
                                    r_db = db.query(ExclusionRule).filter(ExclusionRule.id == rule_id).first()
                                    if r_db:
                                        db.delete(r_db)
                                        db.commit()
                                        refresh_rules()
                                        refresh_excluded_grid()
                                        
                                ui.button(icon='delete', on_click=lambda e, rid=r.id: delete_rule(rid)).props('flat dense color=red round size=sm')

            refresh_rules()
        
        # Apply Button
        async def reapply_rules():
            # Apply rules to EXISTING transactions
            active_rules = db.query(ExclusionRule).filter(ExclusionRule.is_active == True).all()
            txs = db.query(Transaction).all()
            
            import re
            
            count = 0
            excluded_count = 0
            for tx in txs:
                excluded = False
                for r in active_rules:
                    if r.rule_type == 'exact_match':
                        if r.value.lower() == tx.description.lower():
                            excluded = True; break
                    elif r.rule_type == 'regex':
                        try:
                            if re.search(r.value, tx.description, re.IGNORECASE):
                                excluded = True; break
                        except: pass
                    elif r.rule_type == 'contains':
                        if r.value.lower() in tx.description.lower():
                            excluded = True; break

                if tx.is_excluded != excluded:
                    tx.is_excluded = excluded
                    count += 1
                
                if excluded:
                    excluded_count += 1
            
            db.commit()
            refresh_excluded_grid()
            ui.notify(f"Updated {count} transactions. {excluded_count} total excluded.", type='positive')

        ui.button('Apply Rules to Database', on_click=reapply_rules).classes('mt-4').props('outline color=primary')
        
        # Batch Import Button Redirect
        ui.button('Batch Import CSV', on_click=lambda: ui.navigate.to('/excluded/batch')).classes('mt-4 ml-2').props('flat color=secondary')


    # --- Section 2: Excluded Transactions ---
    with ui.card().classes('w-full p-4'):
        ui.label('Excluded Transactions').classes('text-xl font-bold mb-2')
        ui.label('These items are currently hidden.').classes('text-sm text-gray-500 mb-4')
        
        # Header Row
        with ui.row().classes('w-full items-center justify-between mb-2'):
            excluded_count = ui.label('').classes('text-sm text-gray-600')
            
            async def restore_selected():
                rows = await excluded_grid.get_selected_rows()
                if not rows: 
                    ui.notify("No rows selected", type="warning")
                    return
                
                ids = [r['id'] for r in rows]
                db.query(Transaction).filter(Transaction.id.in_(ids)).update({Transaction.is_excluded: False}, synchronize_session=False)
                db.commit()
                refresh_excluded_grid()
                ui.notify(f"Restored {len(ids)} transactions.")

            ui.button('Restore Selected', on_click=restore_selected).props('dense outline color=primary')

        # Fetch initial data
        ex_txs = db.query(Transaction).filter(Transaction.is_excluded == True).order_by(Transaction.date.desc()).all()
        initial_rows = [{
            'id': t.id,
            'date': t.date.strftime('%Y-%m-%d'),
            'description': t.description,
            'amount': t.amount,
            'source': t.source_file or t.account_name
        } for t in ex_txs]
        
        excluded_count.text = f"Showing {len(initial_rows)} excluded transactions" if initial_rows else "No excluded transactions"

        excluded_grid = ui.aggrid({
            'defaultColDef': {'sortable': True, 'filter': True, 'resizable': True, 'suppressHeaderMenuButton': True},
            'columnDefs': [
                {'headerName': 'Date', 'field': 'date', 'sort': 'desc', 'width': 120},
                {'headerName': 'Description', 'field': 'description', 'width': 400},
                {'headerName': 'Amount', 'field': 'amount', 'width': 120},
                {'headerName': 'Source', 'field': 'source', 'width': 200},
                {'headerName': '', 'field': 'action', 'checkboxSelection': True, 'width': 50, 'maxWidth': 50} 
            ],
            'rowData': initial_rows,
            'rowSelection': 'multiple',
            'pagination': True,
            'paginationPageSize': 50,
        }).classes('w-full h-[600px]')

        def refresh_excluded_grid():
            ex_txs = db.query(Transaction).filter(Transaction.is_excluded == True).order_by(Transaction.date.desc()).all()
            rows = [{
                'id': t.id,
                'date': t.date.strftime('%Y-%m-%d'),
                'description': t.description,
                'amount': t.amount,
                'source': t.source_file or t.account_name
            } for t in ex_txs]
            excluded_grid.options['rowData'] = rows
            excluded_grid.update()
            excluded_count.text = f"Showing {len(rows)} excluded transactions" if rows else "No excluded transactions"
        
        async def restore_selected_old():
            # Old function signature preserved but unused, logic moved to button above
            pass
            
        # ui.button('Restore Selected', on_click=restore_selected).classes('mt-2')


