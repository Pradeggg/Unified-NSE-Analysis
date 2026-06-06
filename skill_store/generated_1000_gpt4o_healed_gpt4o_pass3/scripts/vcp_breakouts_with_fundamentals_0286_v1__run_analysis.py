def run(context):
    vcp_picks_data = context.get('vcp_picks_data', [])
    vcp_picks_data = sorted(vcp_picks_data, key=lambda x: (x.get('vcp_score', 0), x.get('enhanced_fund_score', 0)), reverse=True)
    ranked_candidates = [{'symbol': v['symbol'], 'score': v['vcp_score']} for v in vcp_picks_data if v.get('vcp_score') and v.get('enhanced_fund_score')]
    return {'ranked_candidates': ranked_candidates}