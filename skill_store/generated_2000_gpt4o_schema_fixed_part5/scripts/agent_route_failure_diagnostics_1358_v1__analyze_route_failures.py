def run(context):
    # Analyze input for route failures
    failure_modes = []
    for row in context['inputs']:
        if row['universe_size'] != row['stocks_analyzed']:
            failure_modes.append({'run_id': row['run_id'], 'issue': 'Mismatch in universe size and analyzed stocks'})
    return {'failure_modes': failure_modes}