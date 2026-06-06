def run(context):
    broken_links = []
    missing_data = []
    for report in context.get('enhanced_runs_data', []):
        if 'http' not in report.get('notes', '') or report.get('stocks_analyzed', 0) == 0:
            broken_links.append(report['run_id'])
    for stock in context.get('filtered_stocks_data', []):
        if stock.get('current_price') is None:
            missing_data.append(stock['symbol'])
    return {'broken_links': broken_links, 'missing_data': missing_data}