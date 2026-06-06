def run(context):
    holdings_df = context.inputs['holdings']
    snapshots_df = context.inputs['stage_snapshots']
    # Perform analysis
    # Identify potential add and trim candidates
    return {
        'portfolio_state': [],
        'sector_exposure': [],
        'add_candidates': [],
        'trim_candidates': [],
        'risk_flags': []
    }