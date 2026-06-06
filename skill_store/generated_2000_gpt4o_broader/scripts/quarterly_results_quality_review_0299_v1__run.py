def run(context):
    results_data = context['results_data']
    analysis_data = context['analysis_data']
    ranked = sorted(results_data, key=lambda x: x['revenue'] + x['pat'], reverse=True)
    return {'ranked_companies': ranked}