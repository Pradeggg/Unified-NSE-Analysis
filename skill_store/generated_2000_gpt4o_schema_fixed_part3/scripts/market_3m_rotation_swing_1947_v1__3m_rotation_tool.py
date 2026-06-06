def run(context):
    index_data = context['index_data']
    stage_data = context['stage_data']
    # Insert analytical logic here
    return {'comparison_matrix': index_data.join(stage_data)}