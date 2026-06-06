

def run(context):
    # Example of computing a ranking based on growth metrics
    data = context['scores.results_analysis']
    ranked = sorted(data, key=lambda x: (x['growth_yoy_revenue_pct'], x['growth_qoq_revenue_pct']), reverse=True)
    return {'ranked_symbols': [item['symbol'] for item in ranked]}
