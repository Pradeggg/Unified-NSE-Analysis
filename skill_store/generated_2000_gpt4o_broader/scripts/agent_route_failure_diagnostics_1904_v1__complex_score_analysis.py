def run(context):
    table = context.get('table_name')
    data = context.fetch_data(table)
    return [row for row in data if row['stage_score'] >= 80]