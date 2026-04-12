import polars as pl
from dataHub import dataHub
from sqlalchemy import text

# Always comment these lines so you have to verify connections prior to executing
# db_con = dataHub('postgre')
# db_con = dataHub('cockroach')

# ----------------------- Tables

df_tables = pl.read_database(
    """
    SELECT DISTINCT table_schema, table_name
    FROM information_schema.columns
    WHERE column_name = 'season'
        AND table_name NOT LIKE '%%_vw'
        AND table_name NOT ILIKE '%%_retired'
""",
    db_con.db_con,
)

ls_tables = list(df_tables.get_column('table_schema') + '.' + df_tables.get_column('table_name'))


# ----------------------- Dedup block

db_ex = db_con.db_con.connect()
for table in ls_tables:
    df = pl.read_database(
        f"SELECT * FROM {table} WHERE season = '{db_con.cur_season}'",
        db_con.db_con,
        infer_schema_length=None,
    )

    if df.unique().height != df.height:
        print(table)
        db_ex.execute(text(f"DELETE FROM {table} WHERE season = '{db_con.cur_season}'"))
        db_ex.commit()
        df.unique().write_database(table, db_con.db_con, if_table_exists='append')
