def run(context):
    if 'symbol_data' not in context:
        return []
    symbol_data = context['scores.stage2_vcp_picks']
    return [s for s in symbol_data if s['vcp_score'] > 70 and s['vcp_breakout_pct'] > 5]