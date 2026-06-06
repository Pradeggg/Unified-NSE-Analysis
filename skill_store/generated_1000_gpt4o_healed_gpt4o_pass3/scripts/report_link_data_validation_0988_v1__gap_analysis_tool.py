def run(context):
    # Read-only analysis for gap detection
    gaps = []
    if 'report.enhanced_filtered_stocks' not in context:
        return {'error': 'report.enhanced_filtered_stocks table not found.'}
    for stock in context['report.enhanced_filtered_stocks']:
        if stock['current_price'] is None:
            gaps.append(stock['symbol'])
    return {'analysis_gaps': gaps}