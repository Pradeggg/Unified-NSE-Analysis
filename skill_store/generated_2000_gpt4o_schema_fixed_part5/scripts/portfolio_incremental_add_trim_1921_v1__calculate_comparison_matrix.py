

def run(context):
    # Merge holdings with latest stage snapshot
    merged_data = []
    stage_snapshot = context['latest_stage_snapshot']
    holdings = context['current_holdings']
    
    for holding in holdings:
        for stage in stage_snapshot:
            if holding['symbol'] == stage['symbol']:
                merged_data.append({
                    'symbol': holding['symbol'],
                    'qty': holding['qty'],
                    'avg_cost': holding['avg_cost'],
                    'price': stage['price'],
                    'trend_signal': stage['trend_signal'],
                    'trading_signal': stage['trading_signal'],
                    'stage': stage['stage']
                })
    
    # Present data in a way suitable for comparison matrix
    return {'comparison_matrix': merged_data}
