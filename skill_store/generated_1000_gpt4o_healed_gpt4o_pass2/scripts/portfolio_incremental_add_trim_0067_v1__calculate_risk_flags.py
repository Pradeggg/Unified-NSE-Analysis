def run(context):
    risk_flags = []
    avg_relative_strength = context.get('avg_relative_strength', None)
    num_holdings = context.get('num_holdings', 0)
    if avg_relative_strength is not None and avg_relative_strength < 0.5 and num_holdings > 10:
        risk_flags.append('High exposure to underperforming sector')
    return {'risk_flags': risk_flags}