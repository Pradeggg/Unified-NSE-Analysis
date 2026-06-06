def run(context):
    # Example Python tool for complex analysis
    signals = context.inputs['signals_data']
    sector = context.inputs['sector_data']
    comparison_result = {'outperforming': [], 'underperforming': []}
    for signal in signals:
        sector_avg = sector.get(signal['sector'], None)
        if sector_avg:
            if signal['return_pct'] > sector_avg:
                comparison_result['outperforming'].append(signal)
            elif signal['return_pct'] < sector_avg:
                comparison_result['underperforming'].append(signal)
    return comparison_result