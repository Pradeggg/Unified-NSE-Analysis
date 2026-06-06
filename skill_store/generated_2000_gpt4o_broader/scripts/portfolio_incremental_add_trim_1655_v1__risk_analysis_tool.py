def run(context):
    # Extract data from context inputs
    portfolio_state = context['portfolio_state']
    sector_exposure = context['sector_exposure']
    # Example logic for identifying risk flags
    risk_flags = []
    for holding in portfolio_state:
        if holding['stage_score'] < 50 and holding['qty'] > 100:
            risk_flags.append({'symbol': holding['symbol'], 'risk': 'High'})
    return risk_flags