def run(context):
    sector_ranks = context['sector_data'].sort_values(by='change_5d', ascending=False)
    improving_sectors = sector_ranks[sector_ranks['stage2_pct'] > 0.5]
    candidate_symbols = context['stage_data'][(context['stage_data']['stage'] == 2) & (context['stage_data']['relative_strength'] > 50)]['symbol']
    return {'ranked_sectors': improving_sectors, 'candidate_symbols': candidate_symbols}