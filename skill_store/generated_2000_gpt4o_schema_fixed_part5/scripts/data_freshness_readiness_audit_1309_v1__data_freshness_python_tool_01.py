def run(context):
    freshness_report = {}
    for table, count in context['table_counts'].items():
        if count == 0:
            freshness_report[table] = 'Missing data'
        else:
            freshness_report[table] = 'Data fresh'
    return freshness_report