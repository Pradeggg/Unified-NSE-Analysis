def run(context):
    run_data = context['run_data']
    filtered_stocks_data = context['filtered_stocks_data']
    stage_snapshot_data = context['stage_snapshot_data']
    # Analyze data here to create a diagnostic report...
    return {'diagnostic_report': analysis_result}