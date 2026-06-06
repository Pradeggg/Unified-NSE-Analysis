def run(context):
  outperforming_sectors = []
  underperforming_sectors = []
  for sector in context['sector'].unique():
      sector_data = context[context['sector'] == sector]
      if sector_data['avg_change'].mean() > 0:
          outperforming_sectors.append(sector)
      else:
          underperforming_sectors.append(sector)
  return {'outperforming_sectors': outperforming_sectors, 'underperforming_sectors': underperforming_sectors}