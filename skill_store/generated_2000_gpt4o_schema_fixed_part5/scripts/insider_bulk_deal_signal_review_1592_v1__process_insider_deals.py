def run(context):
    # Extract relevant columns
    df = context['evidence']
    grouped = df.groupby('symbol').agg({'qty': 'sum', 'value_cr': 'sum'})
    top_insiders = grouped.sort_values(by='value_cr', ascending=False).head(5)
    summary = f"Top insiders by value: {top_insiders.to_dict()}"
    return summary