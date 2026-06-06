def run(context):
    results = {}
    for table in context['table_names']:
        query = f"SELECT MAX(trade_date) AS latest_date FROM {table};"
        # Simulate running SQL query and fetching result
        results[table] = simulated_query_execution(query)
    return results