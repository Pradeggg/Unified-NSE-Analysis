def run(context):
    resolved_signals = context['resolved_signals_data']
    comparison_matrix = {}
    # Analyze sector-relative performance
    for entry in resolved_signals:
        sector = entry['sector']
        symbol_performance = {
            'symbol': entry['symbol'],
            'company': entry['company'],
            'return_pct': entry['return_pct'],
            'hit_target': entry['hit_target'],
            'hit_stop': entry['hit_stop']
        }
        if sector not in comparison_matrix:
            comparison_matrix[sector] = []
        comparison_matrix[sector].append(symbol_performance)
    return comparison_matrix