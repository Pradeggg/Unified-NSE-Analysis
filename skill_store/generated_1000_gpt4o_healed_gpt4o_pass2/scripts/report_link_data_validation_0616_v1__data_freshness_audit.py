def run(context):
    # Retrieve and validate latest enhanced report data
    run_metadata = context.get('run_metadata', {})
    stock_entries = context.get('filtered_stock_data', [])
    latest_run_date = run_metadata.get('analysis_date')
    if latest_run_date is None:
        return {'findings': 'Run metadata is missing or incomplete', 'freshness_report': 'Data is stale'}
    is_data_fresh = all(entry.get('day_change_pct') is not None for entry in stock_entries)
    freshness_report = 'Data is fresh' if is_data_fresh else 'Data is stale'
    return {
        'findings': f'Latest run date: {latest_run_date}',
        'freshness_report': freshness_report
    }