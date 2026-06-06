def run(context):
    raw_event_symbols = context['inputs']['raw_event_symbols']
    # Apply filtering logic, example placeholder
    filtered_symbols = [symbol for symbol in raw_event_symbols if len(symbol) > 3]
    return {'filtered_symbols': filtered_symbols}