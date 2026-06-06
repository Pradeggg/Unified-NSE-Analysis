def run(context):
    symbols = context['scores.stage2_vcp_picks']
    insights = []
    for symbol in symbols:
        if symbol['vcp_score'] > 75 and symbol['enhanced_fund_score'] > 70:
            insights.append(symbol)
    return {'insights': insights, 'metrics_summary': 'High-potential stocks based on VCP and fundamentals filtered.'}