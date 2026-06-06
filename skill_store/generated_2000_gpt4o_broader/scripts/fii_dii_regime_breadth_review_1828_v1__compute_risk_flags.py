def run(context): 
    # Mock risk flag computation logic
    if context['flow_context']['fii_net_5d'] > 500 and context['flow_context']['dii_net_5d'] < -500:
        return {'risk_flags': 'Risk-On'}
    else:
        return {'risk_flags': 'Neutral'}