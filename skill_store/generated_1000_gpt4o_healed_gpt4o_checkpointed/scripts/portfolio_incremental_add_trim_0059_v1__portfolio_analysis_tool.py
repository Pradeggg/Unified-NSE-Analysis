def run(context):
    holdings = context['portfolio.holdings']
    snapshots = context['scores.stage_snapshots']
    return {'add_candidates': [], 'trim_candidates': []}