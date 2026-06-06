def run(context):
    stage_scores = context.get('scores.stage_snapshots', [])
    holding_data = context.get('portfolio.holdings', [])
    top_add = [c for c in stage_scores if c.get('stage_score', 0) >= 80]
    top_trim = [h for h in holding_data if any(s.get('symbol') == h.get('symbol') and s.get('stage_score', 0) < 50 for s in stage_scores)]
    return {'ranked_add': top_add, 'ranked_trim': top_trim}