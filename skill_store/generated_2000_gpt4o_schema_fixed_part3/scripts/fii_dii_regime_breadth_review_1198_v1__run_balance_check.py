def run_balance_check(flow_signal, regime, breadth_context):
    if flow_signal == 'BULLISH' and regime == 'BULL' and breadth_context['advances'] > breadth_context['declines']:
        return {'risk_flags': 'Risk-On'}
    else:
        return {'risk_flags': 'Uncertain'}