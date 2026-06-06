def run(context):
    input_data = context.get('scores.stage_snapshots', [])
    gaps_exceptions = []
    for record in input_data:
        if record.get('stage_score', 0) < 50 and record.get('rsi', 0) > 70:
            gaps_exceptions.append(record)
    return {'gaps_exceptions': gaps_exceptions}