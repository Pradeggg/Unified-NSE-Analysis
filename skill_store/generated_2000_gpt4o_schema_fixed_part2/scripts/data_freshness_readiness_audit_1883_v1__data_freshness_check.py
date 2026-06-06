def run(context):
    actions_list = []
    for table, date in context['latest_dates'].items():
        if date < (CURRENT_DATE - INTERVAL '1 day'):
            actions_list.append(f'{table} is outdated.')
    return actions_list