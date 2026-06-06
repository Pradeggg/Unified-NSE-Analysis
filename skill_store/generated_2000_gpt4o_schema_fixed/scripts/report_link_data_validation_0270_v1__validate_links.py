def run(context):
    report_data = context["report_data"]
    broken_links = []
    missing_data = []
    
    for record in report_data:
        if not record.get("link"):
            broken_links.append(record.get("run_id"))
        if not record.get("data"):
            missing_data.append(record.get("run_id"))
            
    return {"broken_links": broken_links, "missing_data": missing_data}