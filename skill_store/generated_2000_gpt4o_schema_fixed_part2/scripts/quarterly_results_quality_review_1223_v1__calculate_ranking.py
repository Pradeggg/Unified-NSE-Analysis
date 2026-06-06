def run(context):
    results = context['company_results']
    ranked = sorted(results, key=lambda x: (-x['growth_qoq_revenue_pct'], x['verdict']))
    return {'ranked_companies': ranked[:5]}