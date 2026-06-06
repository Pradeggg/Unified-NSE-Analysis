def run(context):
    vcp_candidates = context['vcp_picks_data']
    vcp_candidates = sorted(vcp_candidates, key=lambda x: (x['vcp_score'], x['enhanced_fund_score']), reverse=True)
    ranked_candidates = [{'symbol': v['symbol'], 'score': v['vcp_score']} for v in vcp_candidates]
    return ranked_candidates