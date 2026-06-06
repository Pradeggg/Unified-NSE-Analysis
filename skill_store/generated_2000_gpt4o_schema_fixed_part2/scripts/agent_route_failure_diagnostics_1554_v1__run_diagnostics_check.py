def run(context):
    # Extract diagnostic insights from snapshot data
    diagnostics = []
    for symbol in context['symbol_list']:
        snapshot = next((snap for snap in context['latest_snapshots'] if snap['symbol'] == symbol), None)
        if snapshot:
            diagnostics.append({
                'symbol': symbol,
                'stage': snapshot.get('stage', 'UNKNOWN'),
                'signal': snapshot.get('trading_signal', 'N/A')
            })
    return diagnostics