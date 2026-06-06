def run(context):
    # Basic check for VCP on given symbols
    candidates = []
    for datum in context['scores.stage2_vcp_picks']:
        if datum['vcp_score'] > 70 and datum['enhanced_fund_score'] > 50:
            candidates.append(datum)
    return {'vcp_candidates': candidates}