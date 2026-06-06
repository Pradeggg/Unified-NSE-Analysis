def run(context):
    # Process and clean the report data
    return {'clean_data': process_data(context['report_data'])}