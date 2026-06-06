
            def run(context):
                # Execute the SQL queries to gather necessary data
                df = context.db.execute_sql(context.inputs['SQL queries'])
                return df
            