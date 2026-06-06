def run(context):
    # Initialize variables
    add_candidates = []
    trim_candidates = []
    risk_flags = []
    
    # Assuming 'portfolio_state' and 'sector_exposure' are correctly populated
    portfolio_state = context['portfolio_state']
    sector_exposure = context['sector_exposure']
    
    for stock in portfolio_state:
        # Implement logic to identify add and trim candidates
        if stock['stage'] in ['Growth', 'Expansion'] and stock['trend_signal'] == 'Positive':
            add_candidates.append(stock['symbol'])
        elif stock['stage'] in ['Decline', 'Consolidation'] and stock['trend_signal'] == 'Negative':
            trim_candidates.append(stock['symbol'])
        
        # Assess risk flags
        if stock['qty'] * stock['live_price'] > 1000000:
            risk_flags.append(f"High exposure in {stock['symbol']}")
    
    return {
        'add_candidates': add_candidates,
        'trim_candidates': trim_candidates,
        'risk_flags': risk_flags
    }