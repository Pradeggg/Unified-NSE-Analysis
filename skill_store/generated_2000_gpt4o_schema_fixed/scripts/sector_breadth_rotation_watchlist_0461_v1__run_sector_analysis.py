def run(context):
    sectors = context['sector_ranks']
    symbols = extract_top_symbols(sectors)
    return symbols