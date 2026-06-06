def run(context):
    import pandas as pd
    # Simulate database connection and fetching
    query = context['query']
    # For the purpose of the example, let's assume fetching mock data
    result_data = pd.DataFrame({'symbol': ['INFY', 'TCS'], 'insider_score': [85, 90]})
    context['data_frame'] = result_data
    return context