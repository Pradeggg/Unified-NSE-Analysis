def run(context):
    signal_data = context['signal_data']
    # Analyze the data to produce a comparison matrix
    return comparison_matrix(signal_data)