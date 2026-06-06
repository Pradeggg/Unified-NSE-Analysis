def run(context):
    holdings = context['portfolio.holdings']
    snapshots = context['scores.stage_snapshots']
    latest_snapshots = snapshots[snapshots['snapshot_date'] == snapshots['snapshot_date'].max()]
    add_candidates = []
    trim_candidates = []
    for holding in holdings:
        snapshot = latest_snapshots[latest_snapshots['symbol'] == holding['symbol']].iloc[0]
        if snapshot['stage_score'] > certain_threshold:  # Placeholder for a real threshold
            add_candidates.append(holding['symbol'])
        elif snapshot['stage_score'] < certain_threshold:  # Placeholder for a real threshold
            trim_candidates.append(holding['symbol'])
    return {'add_candidates': add_candidates, 'trim_candidates': trim_candidates}