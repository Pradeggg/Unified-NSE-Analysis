def run_risk_analysis(portfolio_analysis):
    # Analyze risk based on trading signals and portfolio exposure
    risk_flags = []
    for row in portfolio_analysis:
        if row['trading_signal'] == 'SELL' and row['qty'] > 0:
            risk_flags.append({'symbol': row['symbol'], 'action': 'consider trimming'})
        elif row['trading_signal'] in ('BUY', 'STRONG_BUY') and row['qty'] == 0:
            risk_flags.append({'symbol': row['symbol'], 'action': 'consider adding'})
    return risk_flags