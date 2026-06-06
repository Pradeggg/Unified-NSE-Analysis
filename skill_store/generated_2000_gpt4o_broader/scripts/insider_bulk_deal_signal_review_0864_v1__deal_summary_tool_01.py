def run(context):
    # summarize the bulk and insider deals as a list
    deal_summary = [{'symbol': row['symbol'], 'qty': row['qty'], 'date': row['alert_date']} for row in context]
    return deal_summary