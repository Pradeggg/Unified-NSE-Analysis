def run(context):
    resolved = []
    for symbol in context['symbols']:
        # Perform mock resolution check
        if symbol in context['scores.stage_snapshots']['symbol'].tolist():
            resolved.append({'symbol': symbol, 'status': 'resolved'})
        else:
            resolved.append({'symbol': symbol, 'status': 'unresolved'})
    return {'resolved_symbols': resolved}