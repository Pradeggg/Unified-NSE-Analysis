def run(context):
    actions = []
    for row in context.get('scores.stage_snapshots', []):
        if row.get('stage_score', 0) > 80 and row.get('technical_score', 0) > 80:
            actions.append({'symbol': row['symbol'], 'action': 'Add Candidate'})
        elif row.get('stage_score', 0) < 40 or row.get('technical_score', 0) < 40:
            actions.append({'symbol': row['symbol'], 'action': 'Trim Candidate'})
    return {'actions': actions}