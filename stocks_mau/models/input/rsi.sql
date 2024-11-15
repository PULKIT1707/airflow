{{ config(
    materialized='table',
    on_schema_change='replace'
) }}

WITH base_data AS (
    SELECT
        date,
        symbol,
        close,
        close - LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS price_change
    FROM {{ source('raw_data', 'stock_prices') }}
),

rsi_calc AS (
    SELECT
        date,
        symbol,
        close,
        price_change,
        CASE 
            WHEN price_change > 0 THEN price_change
            ELSE 0
        END AS gain,
        CASE
            WHEN price_change < 0 THEN ABS(price_change)
            ELSE 0
        END AS loss
    FROM base_data
),

average_gains_and_losses AS (
    SELECT
        date,
        symbol,
        close,
        CASE
            WHEN COUNT(gain) OVER (
                PARTITION BY symbol
                ORDER BY date
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            ) < 14 THEN NULL
            ELSE AVG(gain) OVER (
                PARTITION BY symbol
                ORDER BY date
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            )
        END AS avg_gain,
        CASE
            WHEN COUNT(loss) OVER (
                PARTITION BY symbol
                ORDER BY date
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            ) < 14 THEN NULL
            ELSE AVG(loss) OVER (
                PARTITION BY symbol
                ORDER BY date
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            )
        END AS avg_loss
    FROM rsi_calc
),

rsi_final AS (
    SELECT
        date,
        symbol,
        close,
        avg_gain,
        avg_loss,
        CASE
            WHEN avg_gain IS NULL OR avg_loss IS NULL THEN NULL
            WHEN avg_loss = 0 THEN 100
            ELSE ROUND(100 - (100 / (1 + (avg_gain / avg_loss))), 2)
        END AS rsi
    FROM average_gains_and_losses
)

SELECT  date, symbol, close, rsi
FROM rsi_final
{% if is_incremental() %}
WHERE date > (
    SELECT MAX(date) FROM {{ this }}
    WHERE date IS NOT NULL
)
{% endif %}
ORDER BY date DESC, symbol ASC