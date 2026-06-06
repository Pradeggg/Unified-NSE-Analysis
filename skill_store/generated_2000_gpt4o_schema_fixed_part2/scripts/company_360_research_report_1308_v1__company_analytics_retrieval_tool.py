def run(context):
    symbol = context.inputs['symbol']
    # Fetch and return data from the respective tables
    return {
        'recent_quarterly_results': [],
        'latest_stage_scores': []
    }