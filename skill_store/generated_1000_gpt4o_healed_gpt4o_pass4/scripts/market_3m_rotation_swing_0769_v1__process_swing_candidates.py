def run(context):
    # Extracting top swing candidates based on VCP score and recent performance.
    candidates = context['scores.stage2_vcp_picks'].nlargest(10, 'vcp_score')
    filtered_candidates = candidates[candidates['snapshot_date'] >= context['date_limit']]
    return filtered_candidates