def run(context):
    # Check for stocks with missing recommendation
    result = [row['symbol'] for row in context.query('SELECT symbol FROM report.enhanced_filtered_stocks WHERE run_id = ? AND recommendation IS NULL', [context.inputs['run_id']])]
    return {'missing_symbols': result}