def run(context):
    try:
        recent_runs = context.get('recent_runs', [])
        stock_data = context.get('stock_data', [])
        data_gaps = identify_data_gaps(recent_runs, stock_data)
        return {'data_gaps': data_gaps}
    except Exception as e:
        return {'error': str(e)}


def identify_data_gaps(recent_runs, stock_data):
    gaps = []
    for run in recent_runs:
        if not any(stock['run_id'] == run['run_id'] for stock in stock_data):
            gaps.append(run['run_id'])
    return gaps