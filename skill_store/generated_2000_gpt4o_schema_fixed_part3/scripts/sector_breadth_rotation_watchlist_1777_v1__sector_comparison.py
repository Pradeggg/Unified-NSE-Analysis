def run(context):
    sector_data = context['sector_ranks']
    stock_data = context['candidate_symbols']
    improving_sectors = [sector['sector'] for sector in sector_data if sector['rank'] <= 5]
    return improving_sectors