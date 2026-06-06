def run(context):
    exposure_value = context['qty'] * context['market_price']
    return {'exposure_value': exposure_value}