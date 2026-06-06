def run(context):
    # Dummy implementation: Detailed assessment logic
    return 'risk_on' if context['flow_signal'] == 'inflow' and context['regime'] == 'BULL' else 'risk_off'