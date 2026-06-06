def run(context):
    run_data = context['run_data']
    stock_data = context['stock_data']
    # Process the data strictly read-only to produce validation results
    validation_result = []
    for run in run_data:
        related_stocks = [s for s in stock_data if s['run_id'] == run['run_id']]
        if not related_stocks:
            validation_result.append({'run_id': run['run_id'], 'issue': 'No related stocks found'})
    return validation_result