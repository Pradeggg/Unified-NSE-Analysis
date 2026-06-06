def run(context):
    # Read-only analysis for gap detection
    gaps = []
    for stock in context['report.enhanced_filtered_stocks']:
        if stock['current_price'] is None:
            gaps.append(stock['symbol'])
    return {'analysis_gaps': gaps}