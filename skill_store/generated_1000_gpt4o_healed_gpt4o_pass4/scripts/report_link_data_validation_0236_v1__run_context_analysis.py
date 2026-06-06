# Validate data consistency

def run(context):
    findings = []
    verifications = []
    for run in context.get('runs', []):
        if not validate_run_data(run):
            findings.append({"issue": "Data inconsistency detected", "run_id": run['run_id']})
        else:
            verifications.append({"status": "Data verified", "run_id": run['run_id']})
    return {"findings": findings, "verification": verifications}

def validate_run_data(run):
    # Placeholder function to check data consistency
    return True