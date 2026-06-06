from datetime import datetime

def run(context):
    last_trade_date = datetime.strptime(context['last_trade_date'], '%Y-%m-%d')
    current_date = datetime.strptime(context['current_date'], '%Y-%m-%d')
    days_difference = (current_date - last_trade_date).days
    return {'days_difference': days_difference}