def run(context):
    results = []
    for record in context['scores.stage_snapshots']:
        trend_consistency = 'stable' if record['stage_score'] > 50 else 'volatile'
        volatility_status = 'high' if record['change_1d_pct'] > 5 else 'low'
        results.append({'trend_consistency': trend_consistency, 'volatility_status': volatility_status})
    return results;