def run(context):
    current_date = date.today()
    freshness_matrix = {}
    missing_sources = []
    blocking_gaps = []
    loader_actions = []

    tables = ['index_eod', 'equity_eod', 'stage_snapshots', 'market_daily', 'ma_pct_above', 'enhanced_runs']
    for table in tables:
        last_update = context.get(f'{table}_freshness', current_date)
        freshness_matrix[table] = last_update
        if (current_date - last_update).days > 1:
            missing_sources.append(table)
            blocking_gaps.append(f'{table} data is older than expected')
            loader_actions.append(f'Investigate data flow for {table}')

    return {
        'freshness_matrix': freshness_matrix,
        'missing_sources': missing_sources,
        'blocking_gaps': blocking_gaps,
        'loader_actions': loader_actions
    }