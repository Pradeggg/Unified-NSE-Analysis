def run_freshness_check(trade_dates):
    current_date = max(trade_dates)
    outdated_sources = {sector: count for sector, count in trade_dates.items() if (current_date - count.date()).days > 1}
    return outdated_sources