def run(context):
    candidates = []
    for datum in context.get('scores.stage2_vcp_picks', []):
        if datum.get('vcp_score', 0) > 70 and datum.get('enhanced_fund_score', 0) > 50:
            candidates.append(datum)
    return {'vcp_candidates': candidates}