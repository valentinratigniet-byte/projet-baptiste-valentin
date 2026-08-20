select
    (data->>'timestamp')::timestamp as event_ts,
    data->>'event_type' as event_type,
    data->>'niveau' as niveau,
    (data->>'client_id')::int as client_id,
    data->>'session_id' as session_id,
    (data->>'produit_id')::int as produit_id
from {{ source('raw', 'logs_app_events') }}
