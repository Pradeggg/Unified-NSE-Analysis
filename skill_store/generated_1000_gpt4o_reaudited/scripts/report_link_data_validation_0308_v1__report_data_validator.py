def run(context):
    outdated_reports = []
    stocks_with_missing_data = []
    # Example pseudo-code structure for validation
    # for run in context.enhanced_runs:
    #     if run.run_ts <= today:
    #         outdated_reports.append(run.run_id)
    # for stock in context.enhanced_filtered_stocks:
    #     if stock.current_price is None:
    #         stocks_with_missing_data.append(stock.symbol)
    return outdated_reports, stocks_with_missing_data