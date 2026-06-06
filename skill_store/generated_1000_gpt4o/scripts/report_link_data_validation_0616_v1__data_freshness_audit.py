def run(context):
    # Example logic for freshness auditing
    latest_run_date = context['run_metadata']['analysis_date']
    stock_entries = context['filtered_stock_data']
    is_data_fresh = all(entry['day_change_pct'] != None for entry in stock_entries)
    return {
        'findings': f'Latest run date: {latest_run_date}',
        'freshness_report': 'Data is fresh' if is_data_fresh else 'Data is stale'
    }