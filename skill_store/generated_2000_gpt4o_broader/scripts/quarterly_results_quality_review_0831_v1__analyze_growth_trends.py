def run(context):
    return {'growth_trend_analysis': 'positive' if context['growth_yoy_revenue_pct'] > 0 and context['growth_yoy_pat_pct'] > 0 else 'negative'}