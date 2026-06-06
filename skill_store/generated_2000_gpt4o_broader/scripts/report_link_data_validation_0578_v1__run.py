def run(stock_data):
    missing_data = [stock for stock in stock_data if not stock['day_change_pct']]
    return {'missing_data': missing_data}