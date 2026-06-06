def run(context):
    import pandas as pd
    # Assume context['scores.stage_snapshots'] is a DataFrame
    df = context['scores.stage_snapshots']
    recent_df = df[df['snapshot_date'] >= (pd.Timestamp.now() - pd.Timedelta('90 days'))]
    leading_sectors = (recent_df.groupby('sector')['stage_score']
                       .mean()
                       .sort_values(ascending=False)
                       .head(5)
                       .index
                       .tolist())
    return {'leading_sectors': leading_sectors}