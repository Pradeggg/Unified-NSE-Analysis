def run(context):
    latest_dates = context['latest_dates']
    current_date = datetime.datetime.now().date()
    staleness = [current_date - date for date in latest_dates]
    staleness_index = sum(staleness).days / len(staleness)
    return {'staleness_index': staleness_index}