# Sample code to generate a debug trace

def run(context):
    run_id = context['run_id']
    debug_trace = []
    debug_trace.append(f'Checking run_id: {run_id}')
    # Additional code to analyze the report execution
    return {'debug_trace': debug_trace}