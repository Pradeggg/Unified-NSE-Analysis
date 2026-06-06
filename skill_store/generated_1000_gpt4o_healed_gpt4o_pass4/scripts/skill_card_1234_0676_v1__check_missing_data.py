def run(context):
    missing_symbols = []
    if 'report.enhanced_filtered_stocks' in context:
        for row in context['report.enhanced_filtered_stocks']:
            if row.get('run_id') == context.inputs.get('run_id') and row.get('recommendation') is None:
                missing_symbols.append(row.get('symbol'))
    return {'missing_symbols': missing_symbols}