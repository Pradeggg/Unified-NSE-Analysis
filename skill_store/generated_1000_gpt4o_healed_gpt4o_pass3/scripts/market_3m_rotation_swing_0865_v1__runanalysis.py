def run(context):
    index_returns = context.get('index_returns')
    sector_leadership = context.get('sector_leadership')
    swing_candidates = context.get('swing_candidates')

    action_watchlist = context.get('process_action_watchlist', lambda sl, sc: [])(sector_leadership, swing_candidates)
    risk_assessment = context.get('assess_risks', lambda ir: [])(index_returns)

    return {
        "action_watchlist": action_watchlist,
        "risk_assessment": risk_assessment
    }