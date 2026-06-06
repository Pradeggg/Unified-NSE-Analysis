def run(context):
    # Evaluate risk factors based on portfolio state and sector exposure
    return evaluate_risk(context['portfolio_state'], context['sector_exposure'])