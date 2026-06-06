def run(context):
    insights = []
    snapshots = context['scores.stage_snapshots']
    for record in snapshots:
        if record.get('enhanced_fund_score', 0) > 70:
            insights.append(record)
    return {'insights': insights, 'metrics_summary': 'High-potential stocks based on fundamentals filtered.'}