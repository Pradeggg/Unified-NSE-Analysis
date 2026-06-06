def run(context):
    ranked_companies = sorted(context, key=lambda x: x['growth_yoy_revenue_pct'], reverse=True)
    return ranked_companies