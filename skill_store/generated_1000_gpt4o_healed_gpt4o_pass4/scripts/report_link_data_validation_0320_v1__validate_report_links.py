def run(context):
  # Simulate checking report links
  invalid_links = []
  # Imagine validation logic here...
  for link in context.get('report_links', []):  # Using get method for safety
    if 'invalid' in link:  # Example condition
      invalid_links.append(link)
  return {'invalid_links': invalid_links}