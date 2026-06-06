def run(context):
    holdings_data = context['portfolio.holdings']
    snapshots_data = context['scores.stage_snapshots']
    # Implement logic to review holdings and derive portfolio state, add/trim candidates, and risk flags
    portfolio_state = {}
    add_candidates = []
    trim_candidates = []
    risk_flags = []
    return {
        'portfolio_state': portfolio_state,
        'add_candidates': add_candidates,
        'trim_candidates': trim_candidates,
        'risk_flags': risk_flags
    }