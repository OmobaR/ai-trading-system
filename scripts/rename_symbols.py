@"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.events.event_store import EventStore
from src.config.settings import config

store = EventStore({
    'host': config.DB_HOST,
    'port': config.DB_PORT,
    'database': config.DB_NAME,
    'user': config.DB_USER,
    'password': config.DB_PASSWORD
})

updates = [
    ('BREAKX 600', 'BreakX 600'),
    ('BREAKX 1200', 'BreakX 1200'),
    ('BREAKX 1800', 'BreakX 1800'),
    ('GAINX 400', 'GainX 400'),
    ('GAINX 600', 'GainX 600'),
    ('GAINX 800', 'GainX 800'),
    ('GAINX 999', 'GainX 999'),
    ('GAINX 1200', 'GainX 1200'),
    ('PAINX 400', 'PainX 400'),
    ('PAINX 600', 'PainX 600'),
    ('PAINX 800', 'PainX 800'),
    ('PAINX 999', 'PainX 999'),
    ('PAINX 1200', 'PainX 1200'),
    ('FLIPX 1', 'FlipX 1'),
    ('FLIPX 2', 'FlipX 2'),
    ('FLIPX 3', 'FlipX 3'),
    ('FLIPX 4', 'FlipX 4'),
    ('FLIPX 5', 'FlipX 5'),
    ('FX VOL 20', 'FX Vol 20'),
    ('FX VOL 40', 'FX Vol 40'),
    ('FX VOL 60', 'FX Vol 60'),
    ('FX VOL 80', 'FX Vol 80'),
    ('FX VOL 99', 'FX Vol 99'),
    ('SFX VOL 20', 'SFX Vol 20'),
    ('SFX VOL 40', 'SFX Vol 40'),
    ('SFX VOL 60', 'SFX Vol 60'),
    ('SFX VOL 80', 'SFX Vol 80'),
    ('SFX VOL 99', 'SFX Vol 99'),
    ('TRENDX 600', 'TrendX 600'),
    ('TRENDX 1200', 'TrendX 1200'),
    ('TRENDX 1800', 'TrendX 1800'),
    ('SWITCHX 600', 'SwitchX 600'),
    ('SWITCHX 1200', 'SwitchX 1200'),
    ('SWITCHX 1800', 'SwitchX 1800'),
    ('FX', 'FX Vol 20'),
]

with store.conn.cursor() as cur:
    for old, new in updates:
        cur.execute("UPDATE ohlcv_data SET symbol = %s WHERE symbol = %s", (new, old))
        print(f"Updated {cur.rowcount} rows from '{old}' to '{new}'")
    store.conn.commit()

print("✅ Renaming complete.")
"@ | Out-File -FilePath rename_symbols.py -Encoding utf8