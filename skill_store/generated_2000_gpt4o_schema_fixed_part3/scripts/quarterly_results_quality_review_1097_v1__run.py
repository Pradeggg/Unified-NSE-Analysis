# Maintain read-only operations and parameterized queries to avoid SQL injection vulnerabilities

import pandas as pd


def run(context):
    db = context['db_connection']
    params = context['query_params']
    queries = params['queries']

    # Execute each query and collect results
    results = {}
    for name, query in queries.items():
        df = pd.read_sql_query(query, con=db)
        results[name] = df.to_dict(orient='records')
    
    return results