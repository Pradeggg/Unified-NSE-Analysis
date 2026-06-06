def run(context):
    trim_candidates = []
    for record in context['sql_output']:
        if record['qty'] > 100:
            trim_candidates.append(record['symbol'])
    return {'trim_candidates': trim_candidates}