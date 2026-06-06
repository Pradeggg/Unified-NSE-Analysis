def run(context):
    resolved_symbols = set(context.tables['report.enhanced_filtered_stocks']['symbol'])
    unresolved = [s for s in context.inputs['symbols'] if s not in resolved_symbols]
    return {'unresolved_symbols': unresolved}