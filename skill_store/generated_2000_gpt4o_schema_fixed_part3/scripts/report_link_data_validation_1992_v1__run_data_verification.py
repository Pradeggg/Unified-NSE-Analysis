# Example Python tool for validation
import pandas as pd

def run(context):
    report_data = pd.DataFrame(context['report.enhanced_runs'])
    stock_data = pd.DataFrame(context['report.enhanced_filtered_stocks'])
    verified_stocks = stock_data[stock_data['recommendation'].notnull()]
    missing_reports = report_data[~report_data['run_id'].isin(stock_data['run_id'])]
    return {
        'verified_stocks': verified_stocks,
        'missing_reports': missing_reports
    }