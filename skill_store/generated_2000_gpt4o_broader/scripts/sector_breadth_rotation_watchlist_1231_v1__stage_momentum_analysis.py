def run(context):
    # This function should filter symbols in stage 2 and recent momentum
    # Gathering snapshot data within the given date range
    symbols = context.query('SELECT DISTINCT symbol FROM scores.stage_snapshots WHERE stage = 2 AND snapshot_date BETWEEN :start_date AND :end_date')
    return {'stage2_participation': symbols}