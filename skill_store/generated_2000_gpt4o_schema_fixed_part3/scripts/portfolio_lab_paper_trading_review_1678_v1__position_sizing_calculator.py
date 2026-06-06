def run(entry_price, stop_loss, risk_percentage):
    risk_amount = (entry_price - stop_loss)
    position_size = (risk_percentage / 100) / risk_amount
    return position_size