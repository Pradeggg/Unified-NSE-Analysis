def run(context):
    missing_tools = []  # Example: Validate inputs
    for tool in context['tools']:
        if tool not in context['symbols']:
            missing_tools.append(tool)
    return {'validations': missing_tools}