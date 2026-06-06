# This Python tool checks for data consistency in the recent date ranges
# Returns freshness matrix and missing sources as needed

class FreshnessChecker:
    def run(self, context):
        max_index_date = context['latest_index_data'].iloc[0]['trade_date']
        max_equity_date = context['latest_equity_data'].iloc[0]['trade_date']

        freshness_matrix = {'index': max_index_date, 'equity': max_equity_date}
        missing_sources = []

        if max_index_date != max_equity_date:
            missing_sources.append("Data mismatch between index and equity dates.")

        return {'freshness_matrix': freshness_matrix, 'missing_sources': missing_sources}

# Please provide the context from the data fetch operations before running.

freshness_checker = FreshnessChecker()