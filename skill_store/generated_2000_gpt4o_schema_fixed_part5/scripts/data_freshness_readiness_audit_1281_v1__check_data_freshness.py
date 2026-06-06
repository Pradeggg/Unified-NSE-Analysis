def run(context):
    current_date = datetime.datetime.now().date()
    staleness_summary = {}
    for k, v in context.items():
        delta = current_date - v
        staleness_summary[k] = delta.days
    return staleness_summary