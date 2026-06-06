
def run(context):
    run_id = context.get('run_id')
    if run_id is not None:
        query = f"SELECT COUNT(symbol) FROM report.enhanced_filtered_stocks WHERE run_id = '{run_id}';"
        result = context.read_only_query(query)
        return {'filtered_count': result[0][0] if result else 0}
    return {'filtered_count': 0}
