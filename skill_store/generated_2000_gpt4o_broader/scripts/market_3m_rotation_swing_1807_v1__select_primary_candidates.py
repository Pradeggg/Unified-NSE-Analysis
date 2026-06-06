def run(context):
    # List top VCP candidates based on VCP scores and recent performance metrics
    candidate_list = context['scores.stage2_vcp_picks']
    sorted_candidates = sorted(candidate_list, key=lambda x: (x['vcp_score'], x['relative_strength']), reverse=True)
    top_candidates = sorted_candidates[:10]  # Select top 10
    return {'primary_candidates': top_candidates}