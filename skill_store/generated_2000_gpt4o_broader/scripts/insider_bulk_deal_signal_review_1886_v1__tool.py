def run(context):
    alerts = context['recent_insider_alerts']
    deals = context['recent_bulk_deals']
    # Filter logic here
    return {'filtered_symbols': set(alert['symbol'] for alert in alerts).intersection(deal['symbol'] for deal in deals)}