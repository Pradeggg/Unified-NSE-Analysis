def run(symbol_data):
    return [s for s in symbol_data if s['vcp_score'] > 70 and s['vcp_breakout_pct'] > 5]