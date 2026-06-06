def run(context):
    results = context.inputs['results_data']
    analysis_summary = []
    for result in results:
        if result['verdict'] == 'beat' and result['growth_qoq_revenue_pct'] > 10:
            analysis_summary.append({'symbol': result['symbol'], 'note': 'Strong QoQ revenue growth'})
        elif result['verdict'] == 'miss' and result['opm_delta_pp'] < -5:
            analysis_summary.append({'symbol': result['symbol'], 'note': 'Significant decline in OPM'})
    return {'analysis_summary': analysis_summary}