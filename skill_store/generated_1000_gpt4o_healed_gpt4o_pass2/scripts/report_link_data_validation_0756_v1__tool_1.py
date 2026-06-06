
def run(context):
    query = 'SELECT COUNT(symbol) FROM report.enhanced_filtered_stocks WHERE run_id = ?;'
    result = context.execute(query, context.inputs['run_id'])
    return {'filtered_count': result[0][0]}
