def run(context):
    growth_yoy = context['growth_yoy_revenue_pct']
    growth_qoq = context['growth_qoq_revenue_pct']
    trend = 'upward' if growth_qoq > 0 else 'downward'
    alert = growth_yoy > 10 and growth_qoq > 5
    return {'growth_trend': trend, 'alert_flag': alert}