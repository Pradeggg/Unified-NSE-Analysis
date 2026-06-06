def run(context):
    for row in context['snapshot_data']:
        if row['stage_score'] > 80 and row['technical_score'] > 80:
            row['action'] = 'Add Candidate'
        elif row['stage_score'] < 40 or row['technical_score'] < 40:
            row['action'] = 'Trim Candidate'
    return context