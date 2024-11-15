{{ config(
    materialized='table',
    on_schema_change='replace'
) }}

WITH base_data AS (
    SELECT
        date,
        symbol,
        close,
        CASE 
            WHEN COUNT(close) OVER (
                PARTITION BY symbol
                ORDER BY date
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) < 7 THEN NULL
            ELSE ROUND(
                AVG(close) OVER (
                    PARTITION BY symbol
                    ORDER BY date
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ), 2)
        END AS MA_7_DAY
    FROM {{ source('raw_data', 'stock_prices') }}
)

SELECT *
FROM base_data
{% if is_incremental() %}
WHERE date > (
    SELECT MAX(date) FROM {{ this }}
    WHERE date IS NOT NULL
)
{% endif %}
ORDER BY date DESC, symbol ASC



