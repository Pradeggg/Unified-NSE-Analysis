def run(context):
    discrepancies = []
    for entry in context['data']:
        if entry['expected_count'] != entry['actual_count']:
            discrepancies.append({
                'run_id': entry['run_id'],
                'issue': 'Mismatch in filtered stock count',
                'expected': entry['expected_count'],
                'actual': entry['actual_count']
            })
    return {'discrepancy_report': discrepancies}