def run(context):
    # Read-only analysis for VCP risk
    # context contains 'symbol' and 'recent_trend_data'
    risk_score = calculate_risk(context['recent_trend_data'])
    risk_summary = summarize_risk(context['symbol'], risk_score)
    return {'risk_score': risk_score, 'risk_summary': risk_summary}