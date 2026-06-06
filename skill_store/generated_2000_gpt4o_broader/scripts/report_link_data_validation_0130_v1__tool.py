def run(context):
    validate_data = []
    for run in context['report.enhanced_runs']:
        matching_stocks = [stock for stock in context['report.enhanced_filtered_stocks'] if stock['run_id'] == run['run_id']]
        validate_data.append({'run_id': run['run_id'], 'stock_count': len(matching_stocks)})
    return validate_data