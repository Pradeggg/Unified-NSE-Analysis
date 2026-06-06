def run(context):
    sector_ranks = context['sector_ranking']
    improving_sectors = []  # Identify from breadth.sector_daily
    candidate_symbols = []  # Prioritize from scores.stage_snapshots
    # Populate results based on logic
    return sector_ranks, improving_sectors, candidate_symbols