def run(context):
    # Calculate potential based on VCP and other metrics
    vcp_candidates = []  # Placeholder for result
    for entry in context.get_data('scores.stage2_vcp_picks'):
        if entry['vcp_score'] > 5 and entry['enhanced_fund_score'] > 70:
            vcp_candidates.append(entry['symbol'])
    return [{'symbol': symbol, 'vcp_probability': 'High'} for symbol in vcp_candidates]