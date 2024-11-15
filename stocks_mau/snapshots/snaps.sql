{% snapshot dma_snapshot %}
   {{
        config(
            target_schema='analytics',
            unique_key='date || symbol',  
            strategy='timestamp',
            updated_at='date'
        )
    }}

    SELECT
        date AS date,
        symbol AS symbol,
        close AS close,
        ma_7_day AS ma_7_day
    FROM {{ ref('moving_average') }}
{% endsnapshot %}

{% snapshot rsi_snapshot %}
    {{
        config(
            target_schema='analytics',
            unique_key='date || symbol',  
            strategy='timestamp',
            updated_at='date'
        )
    }}

    SELECT
        date AS date,
        symbol AS symbol,
        close AS close,
        rsi AS rsi
    FROM {{ ref('rsi') }}
{% endsnapshot %}