def run(context):
    risk_flags = []
    if context['avg_relative_strength'] < 0.5 and context['num_holdings'] > 10:
        risk_flags.append('High exposure to underperforming sector')
    return {'risk_flags': risk_flags}