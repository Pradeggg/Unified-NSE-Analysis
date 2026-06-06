def run(context):
    # Compute a simple rank based on revenue and PAT growth
    results = context['results']
    ranked = sorted(results, key=lambda x: (x['growth_yoy_revenue_pct'] + x['growth_qoq_revenue_pct'] + x['growth_yoy_pat_pct'] + x['growth_qoq_pat_pct']), reverse=True)
    return {'ranked_companies': [r['symbol'] for r in ranked[:5]]}