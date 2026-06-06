def run(context):
    # Perform diagnostics using symbol and stage
    symbol = context.get('symbol')
    stage = context.get('stage')
    diagnostics = f'Diagnosed symbol {symbol} during {stage} stage.'
    return {'diagnostics': diagnostics}