def run(context):
    symbol_data = context['scores.stage2_vcp_picks']
    snapshot_data = context['scores.stage_snapshots']
    breakout_strength = 'calculated_value'  # Replace with actual logic
    fundamentals_robustness = 'calculated_value'  # Replace with actual logic
    return {'breakout_strength': breakout_strength, 'fundamentals_robustness': fundamentals_robustness}