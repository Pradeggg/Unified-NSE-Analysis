def run(context):
    # Example logic to validate link functioning
    broken_links = []
    missing_data = []
    for run in context['report.enhanced_runs']:
        if not validate_link(run['run_id']):
            broken_links.append(run['run_id'])
    for stock in context['report.enhanced_filtered_stocks']:
        if stock['current_price'] is None:
            missing_data.append(stock['symbol'])
    return {'broken_links': broken_links, 'missing_data': missing_data}