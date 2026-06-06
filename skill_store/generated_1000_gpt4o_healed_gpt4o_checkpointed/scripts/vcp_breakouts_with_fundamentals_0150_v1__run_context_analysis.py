def run(context):
    symbols = context.get('selected_symbols', [])
    if not symbols:
        return {}
    return {'narrative': 'Narrative insights based on selected symbols.'}