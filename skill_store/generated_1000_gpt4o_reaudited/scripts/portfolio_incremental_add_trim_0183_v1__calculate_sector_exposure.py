def run(context):
    holdings_data = context["holdings_data"]
    sector_exposure = holdings_data.groupby('sector')['qty'].sum() / holdings_data['qty'].sum()
    return sector_exposure