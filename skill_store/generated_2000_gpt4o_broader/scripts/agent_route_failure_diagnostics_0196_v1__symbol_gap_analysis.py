def run(context):
    symbols_with_gaps = []
    snapshots = context['scores.stage_snapshots']
    for snapshot in snapshots:
        if 'symbol' not in snapshot['narrative']:
            symbols_with_gaps.append(snapshot['symbol'])
    return {'tool_gap_report': symbols_with_gaps}