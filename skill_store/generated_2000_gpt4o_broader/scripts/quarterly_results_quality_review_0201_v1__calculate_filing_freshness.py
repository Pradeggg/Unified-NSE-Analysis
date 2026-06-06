from datetime import datetime

# Mock function assuming input is provided correctly

def calculate_filing_freshness(filing_date: str, period_end: str) -> int:
    filing_dt = datetime.strptime(filing_date, '%Y-%m-%d')
    period_end_dt = datetime.strptime(period_end, '%Y-%m-%d')
    return (filing_dt - period_end_dt).days
