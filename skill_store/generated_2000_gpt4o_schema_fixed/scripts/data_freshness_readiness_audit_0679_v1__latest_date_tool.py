
required_function = 'run(context)'

def run(context):
    latest_dates = []
    for date_column in context:
        query = f"SELECT MAX({date_column}) AS latest FROM {{table}};"
        # Execute the query in the appropriate environment and append results.
        latest_dates.append(execute_query(query))
    return latest_dates