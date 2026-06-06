def run(context):
    data = context['data']
    debug_info = []
    for record in data:
        message = f"Symbol: {record['symbol']}, OPM: {record['operating_margin']}%, Verdict: {record['verdict']}"
        debug_info.append(message)
    return {'debug_trace': '\n'.join(debug_info)}