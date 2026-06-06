def run(context):
    # Analyze signal outcomes
    outcomes = context['signal_data']
    analysis_summary = {
        'total_signals': len(outcomes),
        'hit_target': sum(1 for o in outcomes if o['hit_target']),
        'hit_stop': sum(1 for o in outcomes if o['hit_stop']),
        'average_return': sum(o['return_pct'] for o in outcomes) / len(outcomes)
    }
    return analysis_summary