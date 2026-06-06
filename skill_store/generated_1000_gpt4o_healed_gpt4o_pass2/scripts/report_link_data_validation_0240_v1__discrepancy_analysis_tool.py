def run(context):
    findings = {}
    last_20_runs = context['report.enhanced_runs']
    filtered_stocks = context['report.enhanced_filtered_stocks']
    run_ids_with_data = set(run['run_id'] for run in last_20_runs)
    filtered_run_ids = set(stock['run_id'] for stock in filtered_stocks)
    missing_run_ids = run_ids_with_data - filtered_run_ids
    if missing_run_ids:
        findings['missing_data'] = list(missing_run_ids)
    empty_field_stocks = [stock for stock in filtered_stocks if any(value in (None, '') for value in stock.values())]
    if empty_field_stocks:
        findings['malformed_data'] = [stock['symbol'] for stock in empty_field_stocks]
    return findings