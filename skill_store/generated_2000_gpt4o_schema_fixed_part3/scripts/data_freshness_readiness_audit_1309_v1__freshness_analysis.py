def run(context):
    last_trade_date = context['last_trade_date']
    if last_trade_date >= context['today']:
        return {'is_fresh': True}
    else:
        return {'is_fresh': False}