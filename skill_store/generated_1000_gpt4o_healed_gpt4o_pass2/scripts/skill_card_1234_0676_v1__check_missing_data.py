def run(context):
    try:
        result = [row['symbol'] for row in context['report.enhanced_filtered_stocks'] if row['run_id'] == context.inputs['run_id'] and row['recommendation'] is None]
        return {'missing_symbols': result}
    except KeyError as e:
        return {'error': str(e)}