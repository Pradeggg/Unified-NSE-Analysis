def run(context):
    latest_runs = context.fetch_data('''SELECT run_id FROM report.enhanced_runs WHERE run_ts = (SELECT MAX(run_ts) FROM report.enhanced_runs)''')
    run_ids = latest_runs['run_id'].tolist()
    # Assuming context has a method fetch_diagnostics which processes these run_ids
    failure_analysis_report = context.fetch_diagnostics(run_ids)
    return failure_analysis_report