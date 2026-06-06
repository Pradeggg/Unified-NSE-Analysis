# Analyze SQL results to produce a debug trace

def run(context):
    results = context['sql_results']
    debug_trace = []
    for result in results:
        trace = {
            'symbol': result['symbol'],
            'sector': result['sector'],
            'hit_target': result['hit_target'],
            'hit_stop': result['hit_stop'],
            'return_pct': result['return_pct']
        }
        debug_trace.append(trace)
    return {'debug_trace': debug_trace}
