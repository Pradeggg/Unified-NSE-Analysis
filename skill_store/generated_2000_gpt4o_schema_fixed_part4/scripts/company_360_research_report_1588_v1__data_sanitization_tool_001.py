def run(context):
    # Example read-only function for data sanitization
    symbol = context['inputs']['symbol']
    # Logic to clean and verify data from provided tables
    return {'cleaned_data': {'symbol': symbol}}