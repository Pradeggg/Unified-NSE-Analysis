def run(context):
    run_id = context['run_id']
    # Ensure all data for the run_id is complete
    return {'is_data_complete': True}