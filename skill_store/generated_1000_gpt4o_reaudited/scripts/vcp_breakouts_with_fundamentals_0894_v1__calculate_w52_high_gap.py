def run(context):
    price = context['price']
    week52_high = context['week52_high']
    return {'w52_high_gap': (week52_high - price) / week52_high * 100}
