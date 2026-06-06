def run(context):
    holdings = context['holding_data']
    snapshots = context['stage_snapshot']
    # Perform analysis logic
    high_risk = snapshots[snapshots['trading_signal'] == 'SELL']
    low_risk = snapshots[snapshots['trading_signal'] == 'BUY']
    return {"high_risk": high_risk.to_dict('records'), "low_risk": low_risk.to_dict('records')}