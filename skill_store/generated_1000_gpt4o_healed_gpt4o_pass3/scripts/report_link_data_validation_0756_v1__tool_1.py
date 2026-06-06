
def run(context):
    valid_run_id = context.inputs.get('run_id')
    if valid_run_id is not None:
        query = f"SELECT COUNT(symbol) FROM report.enhanced_filtered_stocks WHERE run_id = '{valid_run_id}';"
        result = context.read_only_query(query)
        return {'filtered_count': result[0][0]}
    return {'filtered_count': 0}
