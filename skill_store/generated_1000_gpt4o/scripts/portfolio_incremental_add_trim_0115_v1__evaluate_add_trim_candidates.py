def run(context):
    # Implement logic to evaluate add/trim candidates
    snapshots = context['latest_stage_snapshot']
    holdings = context['current_holdings']
    # Process data to identify candidates using risk-first evaluation
    add_candidates = []
    trim_candidates = []
    risk_flags = []
    # Logic here
    return {
        'add_candidates': add_candidates,
        'trim_candidates': trim_candidates,
        'risk_flags': risk_flags
    }