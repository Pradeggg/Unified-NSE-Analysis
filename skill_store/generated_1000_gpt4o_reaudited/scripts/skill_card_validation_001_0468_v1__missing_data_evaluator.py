def run(context):
    evaluated_data = []
    for row in context:
        missing = row['stocks_analyzed'] - row['stocks_filtered']
        evaluated_data.append({'run_id': row['run_id'], 'missing_data': missing})
    return evaluated_data