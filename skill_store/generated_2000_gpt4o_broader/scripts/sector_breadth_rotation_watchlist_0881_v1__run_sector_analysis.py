def run(context):
    sector_breadth_data = context['sector_breadth_data']
    stage2_stock_data = context['stage2_stock_data']
    
    sector_ranks = sorted(sector_breadth_data, key=lambda x: x['breadth_signal'], reverse=True)
    candidate_symbols = [stock for stock in stage2_stock_data if stock['change_1d_pct'] > 0]
    
    return {'sector_ranks': sector_ranks, 'candidate_symbols': candidate_symbols}