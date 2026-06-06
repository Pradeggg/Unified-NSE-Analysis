def run(context):
    broken_links = []
    missing_data = []
    for report in context['enhanced_runs_data']:
        if 'http' not in report['notes'] or report['stocks_analyzed'] == 0:
            broken_links.append(report['run_id'])
    for stock in context['filtered_stocks_data']:
        if stock['current_price'] is None:
            missing_data.append(stock['symbol'])
    return {'broken_links': broken_links, 'missing_data': missing_data}