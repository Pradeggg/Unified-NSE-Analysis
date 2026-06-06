def run(context):
    # Analyze index data to calculate average returns
    return {"index_returns": calculate_index_returns(context['index_data']), "precision": 0.01}