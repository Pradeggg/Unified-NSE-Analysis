def run(context):
    price = context['price']
    change_1d = context['change_1d_pct']
    change_1w = context['change_1w_pct']
    return f"Price: {price}, Daily Change: {change_1d}%, Weekly Change: {change_1w}%"