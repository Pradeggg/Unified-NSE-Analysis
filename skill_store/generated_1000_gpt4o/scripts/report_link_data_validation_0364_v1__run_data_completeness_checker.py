def run(context):
    run_data = context['enhanced_run_data']
    stock_data = context['filtered_stock_data']
    issues = []
    if any(stock['score'] is None for stock in stock_data):
        issues.append('Missing stock scores found.')
    if any(run['stocks_filtered'] < 0 for run in run_data):
        issues.append('Negative stocks filtered found.')
    return {'incomplete_data_issues': issues}