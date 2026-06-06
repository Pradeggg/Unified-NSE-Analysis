# Read-only analysis code to process report data
 def run(context):
     # Sample code to simulate report processing
     results = context.sql_templates
     # Process each SQL result to validate report
     display_results = {'findings': [], 'broken_links': [], 'missing_data': [], 'remediation': [], 'verification': []}
     # Placeholder logic for extracting findings
     for result in results:
         if result: # Simulating condition check
             display_results['findings'].append('Issue found during processing')
     return display_results