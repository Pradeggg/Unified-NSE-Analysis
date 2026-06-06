def run(context):
    recent_runs = context.get('recent_runs', [])
    stock_data = context.get('stock_data', [])
    data_gaps = []
    for run in recent_runs:
        if not any(stock['run_id'] == run['run_id'] for stock in stock_data):
            data_gaps.append(run['run_id'])
    return {'data_gaps': data_gaps}