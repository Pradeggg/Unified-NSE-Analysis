def run(context):
    # Filter for recent VCP candidates with high scores
    candidates = context['scores.stage2_vcp_picks']
    swing_candidates = candidates[(candidates['vcp_score'] > 80) & (candidates['change_1m_pct'] > 5)]
    return swing_candidates[['symbol', 'company_name', 'sector']].to_dict(orient='records')