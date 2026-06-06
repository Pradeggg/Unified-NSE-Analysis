def run(context):
    trade_data = context.get('trade_data', [])
    processed_results = []
    for entry in trade_data:
        processed_entry = {
            'trade_date': entry.get('trade_date'),
            'change_pct': entry.get('change_pct')
        }
        processed_results.append(processed_entry)
    return {'processed_results': processed_results}