
def run(context):
    freshness_exceptions = {}
    for record in context['records']:
        table_name = record['table_name']
        latest_date = record['latest_date']
        if latest_date < context['expected_thresholds'][table_name]:
            freshness_exceptions[table_name] = latest_date
    return freshness_exceptions
