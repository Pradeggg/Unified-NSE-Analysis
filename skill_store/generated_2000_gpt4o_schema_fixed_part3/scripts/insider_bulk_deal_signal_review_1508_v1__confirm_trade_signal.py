def run(context):
    latest_snapshot = max(context['scores.stage_snapshots']['snapshot_date'])
    for record in context['scores.stage_snapshots']:
        if record['symbol'] == context['symbol'] and record['snapshot_date'] == latest_snapshot:
            return record['trading_signal'] in ('BUY', 'STRONG_BUY')
    return False