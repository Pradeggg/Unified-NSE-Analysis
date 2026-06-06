def run(context):
    results = context.inputs['results']
    is_valid = True
    issues = []
    for row in results:
        if row['symbol'] is None:
            is_valid = False
            issues.append(f"Missing symbol for run_id {row['run_id']}")
    return {'is_valid': is_valid, 'issues': issues}