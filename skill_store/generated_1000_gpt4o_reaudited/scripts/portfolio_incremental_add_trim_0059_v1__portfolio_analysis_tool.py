def run(context):
    holdings = context['portfolio.holdings']
    snapshots = context['scores.stage_snapshots']
    # Perform analysis...
    return {'add_candidates': [], 'trim_candidates': []}