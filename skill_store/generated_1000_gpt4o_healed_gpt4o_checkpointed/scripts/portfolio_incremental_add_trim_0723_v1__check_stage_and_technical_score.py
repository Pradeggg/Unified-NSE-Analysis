def run(context):
    for row in context.get('scores.stage_snapshots', []):
        if row.get('stage_score', 0) > 80 and row.get('technical_score', 0) > 80:
            row['action'] = 'Add Candidate'
        elif row.get('stage_score', 0) < 40 or row.get('technical_score', 0) < 40:
            row['action'] = 'Trim Candidate'
    return context