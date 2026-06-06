def execute(context):
    result = context['sql_runner'].execute('SELECT revenue, pat FROM scores.quarterly_results WHERE symbol = %s ORDER BY period_end DESC LIMIT 1', context['symbol'])
    return {'latest_revenue': result[0]['revenue'], 'latest_pat': result[0]['pat']}