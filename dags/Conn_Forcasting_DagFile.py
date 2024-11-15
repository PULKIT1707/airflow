from airflow import DAG
from airflow.decorators import task
from airflow.utils.dates import days_ago
from datetime import timedelta, datetime
from yfinance_to_snowflake import extract_stock_data, load  # Use the available functions
from statsmodels.tsa.arima.model import ARIMA
import snowflake.connector
import pandas as pd
import numpy as np
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def return_snowflake_conn():
    hook = SnowflakeHook(snowflake_conn_id='snowflake_conn')
    conn = hook.get_conn()
    return conn.cursor()

@task
def load90DaysDataToSnowflake(df, symbol, target_table):
    # Use the 'load' function from yfinance_to_snowflake to load the data
    load(df, symbol, target_table)

@task
def predictNext7Days(df):
    df['date'] = pd.to_datetime(df['date'])
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)

    df = df.sort_values(by='date')

    open_prices = df['open'].values
    high_prices = df['high'].values
    low_prices = df['low'].values
    close_prices = df['close'].values
    volume_values = df['volume'].values

    model_open = ARIMA(open_prices, order=(5, 1, 0))
    model_fit_open = model_open.fit()
    forecast_open = model_fit_open.forecast(steps=7)

    model_high = ARIMA(high_prices, order=(5, 1, 0))
    model_fit_high = model_high.fit()
    forecast_high = model_fit_high.forecast(steps=7)

    model_low = ARIMA(low_prices, order=(5, 1, 0))
    model_fit_low = model_low.fit()
    forecast_low = model_fit_low.forecast(steps=7)

    model_close = ARIMA(close_prices, order=(5, 1, 0))
    model_fit_close = model_close.fit()
    forecast_close = model_fit_close.forecast(steps=7)

    model_volume = ARIMA(volume_values, order=(5, 1, 0))
    model_fit_volume = model_volume.fit()
    forecast_volume = model_fit_volume.forecast(steps=7)

    future_dates = [datetime.now() + timedelta(days=i) for i in range(1, 8)]

    forecast_df = pd.DataFrame({
        'date': future_dates,
        'open': forecast_open,
        'high': forecast_high,
        'low': forecast_low,
        'close': forecast_close,
        'volume': np.ceil(forecast_volume),
        'symbol': df['symbol'].iloc[0]
    })

    forecast_df[['open', 'high', 'low', 'close', 'volume']] = forecast_df[['open', 'high', 'low', 'close', 'volume']].round(2)
    return forecast_df

with DAG(
    'stock_price_analytics_extended',
    default_args=default_args,
    description='A DAG to load stock data to Snowflake and run dbt models for stock price analytics',
    schedule_interval='@daily',
    start_date=days_ago(1),
    catchup=False,
) as dag:

    stock_symbols = ["QCOM", "AAPL"]

    target_table = "stock_db.raw_data.stock_prices"

    for stock_symbol in stock_symbols:
        stock_data = extract_stock_data(stock_symbol)        
        load_90_days_data = load90DaysDataToSnowflake(stock_data, stock_symbol, target_table)        
        forecast_data = predictNext7Days(stock_data)

        stock_data >> load_90_days_data >> forecast_data
