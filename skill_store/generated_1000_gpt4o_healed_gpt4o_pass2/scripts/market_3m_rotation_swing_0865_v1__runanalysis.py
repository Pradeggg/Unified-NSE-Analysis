def run(context):
    # Extract required data
    index_returns = context.get('index_returns')
    sector_leadership = context.get('sector_leadership')
    swing_candidates = context.get('swing_candidates')
    
    # Process data to generate analysis
    try:
        action_watchlist = process_action_watchlist(sector_leadership, swing_candidates)
    except NameError:
        action_watchlist = []  # Default to empty if function is undefined
    risk_assessment = assess_risks(index_returns)
    
    return {
        "action_watchlist": action_watchlist,
        "risk_assessment": risk_assessment
    }