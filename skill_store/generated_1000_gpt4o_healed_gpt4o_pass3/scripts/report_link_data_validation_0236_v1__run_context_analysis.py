# Validate data consistency

def run(context):
    findings = []
    for run in context.get('runs', []):
        if not validate_run_data(run):
            findings.append({"issue": "Data inconsistency detected", "run_id": run['run_id']})
    return {"findings": findings}

def validate_run_data(run):
    # Placeholder function to check data consistency
    return True