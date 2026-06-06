def run(context):
    return context.sql("SELECT * FROM market.equity_eod WHERE trade_date = (SELECT MAX(trade_date) FROM market.equity_eod)")