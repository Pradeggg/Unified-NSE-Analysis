def run(context):
    exposure = context['qty'] * (context['current_price'] - context['avg_cost'])
    return {'exposure': exposure}