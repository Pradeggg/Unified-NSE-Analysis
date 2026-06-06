def run(context):
    price = context.get('price')
    week52_high = context.get('week52_high')
    if price is None or week52_high is None:
        return {'error': 'price or week52_high not found in context'}
    return {'w52_high_gap': (week52_high - price) / week52_high * 100}
