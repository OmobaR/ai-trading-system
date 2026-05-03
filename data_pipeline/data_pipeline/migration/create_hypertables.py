"""
One-time migration script to create new hypertable structure.
Run this BEFORE starting the pipeline.
"""
from data_pipeline.core.database import create_all_hypertables
from data_pipeline.core.logger import get_logger

logger = get_logger("migration")


def migrate_create_tables():
    """Create all timeframe-specific hypertables."""
    logger.info("Creating timeframe-specific hypertables...")
    create_all_hypertables()
    logger.info("Migration complete. New tables are ready for data ingestion.")


if __name__ == "__main__":
    migrate_create_tables()
