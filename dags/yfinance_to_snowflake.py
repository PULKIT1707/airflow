# In Cloud Composer, add apache-airflow-providers-snowflake to PYPI Packages
import pandas as pd
from airflow import DAG
from airflow.models import Variable
from airflow.decorators import task
from airflow.operators.python import get_current_context
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from airflow.operators.bash import BashOperator
import snowflake.connector
import requests
from datetime import datetime, timedelta
import yfinance as yf

def is_weekend(date_obj):
    """
    Given a datetime object, returns True if the date is a weekend (Saturday or Sunday), otherwise False.
    """
    return date_obj.weekday() >= 5  # 5 = Saturday, 6 = Sunday

def get_previous_weekday(date_str):
    """
    Given a date string in 'YYYY-MM-DD' format, returns the last weekday (Monday-Friday) as a string in the same format.
    Skips weekends (Saturday and Sunday).
    """
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    while is_weekend(date_obj):
        date_obj -= timedelta(days=1)
    return date_obj.strftime("%Y-%m-%d")

def get_next_weekday(date_str):
    """
    Given a date string in 'YYYY-MM-DD' format, returns the next weekday (Monday-Friday) as a string in the same format.
    Skips weekends (Saturday and Sunday).
    """
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_obj += timedelta(days=1)  # Move forward one day
    while is_weekend(date_obj):
        date_obj += timedelta(days=1)
    return date_obj.strftime("%Y-%m-%d")

def return_snowflake_conn():
    # Initialize the SnowflakeHook
    hook = SnowflakeHook(snowflake_conn_id='snowflake_conn')
    # Execute the query and fetch results
    conn = hook.get_conn()
    return conn.cursor()

def get_logical_date():
    # Get the current context
    context = get_current_context()
    return str(context['logical_date'])[:10]

@task
def extract_stock_data(stock_symbol):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=90)
    
    stock = yf.Ticker(stock_symbol)
    df = stock.history(start=start_date, end=end_date, interval="1d")
    
    df.reset_index(inplace=True)
    df.rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}, inplace=True)
    
    df['symbol'] = stock_symbol
    
    return df

@task
def load(d, symbol, target_table):
    cur = return_snowflake_conn()
    print("inside load:", d)

    try:
        cur.execute(f"""CREATE TABLE IF NOT EXISTS {target_table} (
            date date, open float, close float, high float, low float, volume int, symbol varchar 
        )""")
        cur.execute("BEGIN;")

        for _, row in d.iterrows():
            open_rounded = round(row['open'], 2) if pd.notnull(row['open']) else 'NULL'
            high_rounded = round(row['high'], 2) if pd.notnull(row['high']) else 'NULL'
            low_rounded = round(row['low'], 2) if pd.notnull(row['low']) else 'NULL'
            close_rounded = round(row['close'], 2) if pd.notnull(row['close']) else 'NULL'
            volume_rounded = int(round(row['volume'])) if pd.notnull(row['volume']) else 'NULL'

            merge_query = f"""
            MERGE INTO {target_table} AS target
            USING (
                SELECT '{row['date'].strftime('%Y-%m-%d')}' AS date,
                       {open_rounded} AS open,
                       {high_rounded} AS high,
                       {low_rounded} AS low,
                       {close_rounded} AS close,
                       {volume_rounded} AS volume,
                       '{row['symbol']}' AS symbol
            ) AS source
            ON target.date = source.date AND target.symbol = source.symbol
            WHEN MATCHED THEN
                UPDATE SET
                    open = source.open,
                    high = source.high,
                    low = source.low,
                    close = source.close,
                    volume = source.volume
            WHEN NOT MATCHED THEN
                INSERT (date, open, high, low, close, volume, symbol)
                VALUES (source.date, source.open, source.high, source.low, source.close, source.volume, source.symbol);
            """
            print(f"Executing MERGE query: {merge_query}")
            cur.execute(merge_query)

        cur.execute("COMMIT;") 
    except Exception as e:
        cur.execute("ROLLBACK;") 
        print(f"Error occurred: {e}")
        raise e
    finally:
        cur.close()  


with DAG(
    dag_id = 'YfinanceToSnowflake',
    start_date = datetime(2024,10,2),
    catchup=False,
    tags=['ETL'],
    schedule = '30 2 * * *'
) as dag:
    target_table = "stock_db.raw_data.stock_prices"
    symbols = ["AAPL", "QCOM"] 

    loaded_tasks = []
    for symbol in symbols:
        data = extract_stock_data(symbol)
        load_task = load(data, symbol, target_table)
        loaded_tasks.append(load_task)

    dbt_run = BashOperator(
        task_id='dbt_run',
        bash_command='cd /opt/airflow/stocks_mau && dbt run --profiles-dir /opt/airflow/stocks_mau'
    )

    dbt_test = BashOperator(
        task_id='dbt_test',
        bash_command='cd /opt/airflow/stocks_mau && dbt test --profiles-dir /opt/airflow/stocks_mau'
    )

    dbt_snapshot = BashOperator(
        task_id='dbt_snapshot',
        bash_command='cd /opt/airflow/stocks_mau && dbt snapshot --profiles-dir /opt/airflow/stocks_mau'
    )

    loaded_tasks >> dbt_run >> dbt_test >> dbt_snapshot