def run(context):
    run_id = context['run_id']
    symbol_list = context['symbol_list']
    # Sample read-only integrity check
    query = '''SELECT symbol, current_price FROM report.enhanced_filtered_stocks WHERE run_id = %s AND symbol = ANY(%s)'''
    result = context['database_connection'].execute(query, (run_id, symbol_list))
    return {'integrity_report': result.fetchall()}