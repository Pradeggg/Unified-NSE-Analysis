def run(context):
    # Extract data from SQL execution context
    anomalies = context.sql_results('check_enhanced_report_links')
    # Process anomalies to detect missing links
    return {'findings': [{'run_id': a['run_id'], 'missing_count': a['missing_stock_data']} for a in anomalies if a['missing_stock_data'] > 0]}