def run(context):
    top_add = [c for c in context['stage_scores'] if c['stage_score'] >= 80]
    top_trim = [h for h in context['holding_data'] if h['stage_score'] < 50]
    return {'ranked_add': top_add, 'ranked_trim': top_trim}