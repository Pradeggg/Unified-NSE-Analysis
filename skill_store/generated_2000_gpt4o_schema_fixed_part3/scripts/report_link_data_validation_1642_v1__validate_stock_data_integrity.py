def run(context):
    run_data, stock_data = context['run_data'], context['stock_data']
    # perform data integrity check
    integrity_report = {}
    for run in run_data:
        if run['stocks_filtered'] != len([s for s in stock_data if s['run_id'] == run['run_id']]):
            integrity_report[run['run_id']] = 'Mismatch in stock filtered count'
    return integrity_report