def run(context):
    sorted_sectors = sorted(context['sectors'], key=lambda x: x['breadth_signal'], reverse=True)
    formatted_symbols = [f'NSE:{symbol}' for symbol in context['symbols']]
    return {'sorted_sectors': sorted_sectors, 'formatted_symbols': formatted_symbols}