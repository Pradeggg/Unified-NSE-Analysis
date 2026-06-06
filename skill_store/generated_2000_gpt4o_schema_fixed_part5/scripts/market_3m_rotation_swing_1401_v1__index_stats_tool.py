def run(context):
    import pandas as pd
    index_data = pd.DataFrame(context)
    index_data['returns'] = index_data['close'].pct_change()
    index_returns = index_data.groupby('index_symbol')['returns'].mean().reset_index()
    return index_returns