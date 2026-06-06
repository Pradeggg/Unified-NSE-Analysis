def run(context):
    exceptions = []
    for entry in context:
        if entry['revenue_growth'] > 15 and entry['pat_growth'] > 15:
            exceptions.append(entry['symbol'])
    return exceptions