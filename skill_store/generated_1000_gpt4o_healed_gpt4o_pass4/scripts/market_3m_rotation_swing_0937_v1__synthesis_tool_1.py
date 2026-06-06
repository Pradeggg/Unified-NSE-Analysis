def run(context):
    index_data = context.get('index_returns', [])
    stage_data = context.get('stage_distribution_change', [])
    comparison_matrix = {'index_data': index_data, 'stage_data': stage_data}
    return comparison_matrix