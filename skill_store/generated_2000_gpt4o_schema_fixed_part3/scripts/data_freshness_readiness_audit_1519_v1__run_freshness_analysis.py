def run(context):
    query = '''SELECT table_name, MAX(trade_date) as latest_date
               FROM (
                   SELECT 'market_index' AS table_name, trade_date FROM market.index_eod
                   UNION ALL
                   SELECT 'market_equity', trade_date FROM market.equity_eod
                   UNION ALL
                   SELECT 'stage_snapshots', snapshot_date FROM scores.stage_snapshots
               ) subquery
               GROUP BY table_name;'''
    with context.db.connect() as conn:
        result = conn.execute(query)
    return {row['table_name']: row['latest_date'] for row in result}