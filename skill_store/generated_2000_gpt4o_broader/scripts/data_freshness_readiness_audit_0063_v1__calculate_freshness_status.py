def run(context):
    import datetime
    current_date = datetime.date.today()
    freshness_status = {}
    for source, data in context['freshness_data'].items():
        if data['latest_date'] >= current_date - datetime.timedelta(days=1):
            freshness_status[source] = 'Fresh'
        else:
            freshness_status[source] = 'Stale'
    return freshness_status