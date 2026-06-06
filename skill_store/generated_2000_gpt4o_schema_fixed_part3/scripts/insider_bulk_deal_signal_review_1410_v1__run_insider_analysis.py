def run(context):
    # Analyze and rank symbols based on insider activity and technical data
    sorted_symbols = sorted(context['symbol_data'], key=lambda x: x['insider_score'], reverse=True)
    return sorted_symbols[:5], 'Summary of significant deals.', 'Context of insider actions.'