def run(context):
    # Assume context is a Pandas DataFrame
    context['gap'] = context['trade_date'].diff().dt.days > 1
    return context[context['gap']]['trade_date'].to_list()