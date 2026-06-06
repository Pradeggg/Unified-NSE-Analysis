def run(context):
    returns = context['return_pct']
    risk_assessment = ['High Risk' if r < 0 else 'Low Risk' for r in returns]
    return risk_assessment