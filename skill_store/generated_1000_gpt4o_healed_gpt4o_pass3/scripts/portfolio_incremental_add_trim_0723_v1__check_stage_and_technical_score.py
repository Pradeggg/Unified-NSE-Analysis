def run(context):
    actions = []
    for row in context.get('scores.stage_snapshots', []):
        action = None
        if row.get('stage_score', 0) > 80 and row.get('technical_score', 0) > 80:
            action = 'Add Candidate'
        elif row.get('stage_score', 0) < 40 or row.get('technical_score', 0) < 40:
            action = 'Trim Candidate'
        actions.append({'symbol': row['symbol'], 'action': action})
    return actions