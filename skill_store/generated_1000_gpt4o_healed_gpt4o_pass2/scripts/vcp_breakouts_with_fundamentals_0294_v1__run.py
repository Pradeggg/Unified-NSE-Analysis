
# Example function
# Uses input 'context' to filter and rank stocks based on predefined criteria

def run(context):
    # Filter logic based on Python read-only processing if needed
    if not isinstance(context, list):
        raise ValueError('Input context must be a list')
    filtered_data = []
    for stock_data in context:
        if (stock_data.get('vcp_score', 0) > 80 and
            stock_data.get('enhanced_fund_score', 0) > 70):
            filtered_data.append(stock_data)
    if not filtered_data:
        raise ValueError('No valid stocks found')
    return filtered_data
