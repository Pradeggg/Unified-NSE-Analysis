def run(context):
    # Extract necessary data
    vcp_data = context['scores.stage2_vcp_picks']
    equity_data = context['market.equity_eod']
    # Process and filter top VCP candidates
    filtered_candidates = vcp_data.sort_values(by='vcp_score', ascending=False).head(10)
    return filtered_candidates[['symbol', 'company_name', 'vcp_score']].to_dict(orient='records')