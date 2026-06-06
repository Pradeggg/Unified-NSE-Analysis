def run(context):
    insights = []
    for result in context['verified_results']:
        if result['verdict'] == 'beat' and float(result['opm_pct']) > 20.0:
            insights.append({
                'symbol': result['symbol'],
                'insight': 'Strong operating profit margin driving positive beat.'
            })
    return insights