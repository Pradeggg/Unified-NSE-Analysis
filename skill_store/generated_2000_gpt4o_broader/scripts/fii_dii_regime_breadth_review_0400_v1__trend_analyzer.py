def run(context):
    # Example read-only analysis code
    analyze_trends(context['flow_data'], context['regime_data'], context['breadth_data'], context['index_data'])
    return {'flow_context': {}, 'breadth_context': {}, 'risk_flags': {}}