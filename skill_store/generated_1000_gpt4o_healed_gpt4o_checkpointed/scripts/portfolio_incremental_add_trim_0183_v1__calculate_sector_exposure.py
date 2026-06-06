def run(context):
    import pandas as pd  # Import pandas for DataFrame handling
    holdings = context['portfolio.holdings']
    snapshots = context['scores.stage_snapshots']
    
    # Ensure data is not empty
    if holdings.empty or snapshots.empty:
        return pd.DataFrame()
    
    # Join holdings with snapshots to get current data
    latest_snapshot_date = snapshots['snapshot_date'].max()
    latest_snapshots = snapshots[snapshots['snapshot_date'] == latest_snapshot_date]
    merged_data = pd.merge(holdings, latest_snapshots, on='symbol', how='inner')
    
    # Calculate sector exposure
    sector_exposure = merged_data.groupby('sector')['qty'].sum() / merged_data['qty'].sum()
    return sector_exposure.to_frame().reset_index()