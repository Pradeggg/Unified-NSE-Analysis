def run(context):
    recent_run_notes = context['run_data']['notes']
    if 'missing tool' in recent_run_notes or 'unresolved symbol' in recent_run_notes:
        return {'gap_analysis': 'Potential missing tool or unresolved symbol detected'}
    return {'gap_analysis': 'No gaps detected'}