def run(context):
    recent_failures = [run for run in context['run_data'] if "failure" in run['notes']]
    return {'failure_insights': recent_failures[:5]}