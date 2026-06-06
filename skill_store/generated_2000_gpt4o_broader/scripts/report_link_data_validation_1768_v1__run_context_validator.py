def run(context):
    # Extract and validate report context
    run_id = context.get('run_id')
    # Validate run_id against approved tables:
    if run_id in approved_tables['report.enhanced_runs']['columns']:
        return {'validation_status': 'valid'}
    else:
        return {'validation_status': 'invalid'}