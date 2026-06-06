def run(context):
    return [stock for stock in context if stock['weekly_signal'] is None]