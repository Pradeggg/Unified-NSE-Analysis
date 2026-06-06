def run(context):
    # Extracting top swing candidates based on VCP score and recent performance.
    candidates = context['scores.stage2_vcp_picks'].nlargest(10, 'vcp_score')
    return candidates[candidates['snapshot_date'] >= context['date_limit']]