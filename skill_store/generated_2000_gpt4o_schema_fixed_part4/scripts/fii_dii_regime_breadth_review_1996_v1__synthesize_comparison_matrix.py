def run(context):
    regime_data = context['regime_with_flow']
    breadth_data = context['market_breadth']
    index_data = context['index_confirmation']
    # Synthesize comparison matrix
    matrix = {}
    matrix['regime'] = regime_data['regime']
    matrix['flow_context'] = regime_data['flow_signal']
    matrix['breadth_context'] = f"A: {breadth_data['advances']}, D: {breadth_data['declines']}"
    matrix['index_confirmation'] = index_data['change_pct']
    matrix['risk_flags'] = 'Risk-on' if regime_data['regime'] == 'BULL' else 'Risk-off'
    return matrix