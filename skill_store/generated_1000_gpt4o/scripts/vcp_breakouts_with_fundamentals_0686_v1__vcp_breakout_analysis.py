def run(context):
    # Sample code to analyze VCP breakout strength
    symbol_data = context['approved_tables']['scores.stage2_vcp_picks']
    snapshot_data = context['approved_tables']['scores.stage_snapshots']
    # Process to facilitate analysis
    breakout_strength = ...  # Analysis logic here
    fundamentals_robustness = ...  # Analysis logic here
    return {'breakout_strength': breakout_strength, 'fundamentals_robustness': fundamentals_robustness}