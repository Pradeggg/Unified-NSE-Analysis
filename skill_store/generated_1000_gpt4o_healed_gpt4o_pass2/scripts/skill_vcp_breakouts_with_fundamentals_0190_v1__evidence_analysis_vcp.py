def run(context):
    insights = []
    snapshots = context['scores.stage_snapshots']
    for symbol in snapshots:
        if symbol.get('enhanced_fund_score', 0) > 70:
            insights.append(symbol)
    return {'insights': insights, 'metrics_summary': 'High-potential stocks based on fundamentals filtered.'}