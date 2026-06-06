def run(context):
    stage_scores = context['scores.stage_snapshots']
    holding_data = context['portfolio.holdings']
    top_add = [c for c in stage_scores if c['stage_score'] >= 80]
    top_trim = [h for h in holding_data if any(s['symbol'] == h['symbol'] and s['stage_score'] < 50 for s in stage_scores)]
    return {'ranked_add': top_add, 'ranked_trim': top_trim}