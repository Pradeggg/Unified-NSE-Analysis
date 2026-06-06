def run(context):
    snapshots = context['scores.stage_snapshots']
    holdings = context['portfolio.holdings']
    add_candidates = []
    trim_candidates = []
    risk_flags = []
    # Logic here to evaluate and populate lists
    return {
        'add_candidates': add_candidates,
        'trim_candidates': trim_candidates,
        'risk_flags': risk_flags
    }