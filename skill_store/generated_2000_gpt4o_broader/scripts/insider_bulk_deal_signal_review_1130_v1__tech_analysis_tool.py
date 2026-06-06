def run(context):
    # Analyze technical data to determine accumulation or distribution
    data = context['scores.stage_snapshots']
    results = []
    for entry in data:
        if entry['technical_score'] > 70 and entry['change_1w_pct'] > 0:
            results.append({'symbol': entry['symbol'], 'status': 'Accumulation'})
        else:
            results.append({'symbol': entry['symbol'], 'status': 'Distribution'})
    return results