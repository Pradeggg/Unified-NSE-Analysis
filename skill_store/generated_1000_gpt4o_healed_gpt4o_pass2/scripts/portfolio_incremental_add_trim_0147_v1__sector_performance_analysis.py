def run(context):
    import pandas as pd

    if isinstance(context, pd.DataFrame):
        return context.groupby('sector').mean().to_dict('index')
    else:
        return {'error': 'Invalid input format for sector performance analysis.'}