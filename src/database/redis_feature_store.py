#src/database/redis_feature_store.py
import redis
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FeatureStore:
    def __init__(self, redis_config):
        self.client = redis.Redis(**redis_config)
        try:
            self.client.ping()
            logger.info("Connected to Redis")
        except redis.ConnectionError as e:
            logger.error(f"Error connecting to Redis: {e}")
            raise

    def set_feature(self, symbol, feature_name, value):
        key = f"feature:{symbol}"
        try:
            self.client.hset(key, feature_name, json.dumps(value))
            logger.info(f"Set feature {feature_name} for {symbol}")
        except redis.RedisError as e:
            logger.error(f"Error setting feature: {e}")
            raise

    def get_feature(self, symbol, feature_name):
        key = f"feature:{symbol}"
        try:
            value = self.client.hget(key, feature_name)
            if value:
                return json.loads(value)
            return None
        except redis.RedisError as e:
            logger.error(f"Error getting feature: {e}")
            raise

    def get_all_features(self, symbol):
        key = f"feature:{symbol}"
        try:
            return {k.decode(): json.loads(v) for k, v in self.client.hgetall(key).items()}
        except redis.RedisError as e:
            logger.error(f"Error getting all features: {e}")
            raise

# Example usage
if __name__ == "__main__":
    redis_config = {
        'host': 'localhost',
        'port': 6379,
        'db': 0
    }
    store = FeatureStore(redis_config)
    store.set_feature('VIX75', 'ATR', 1.23)
    store.set_feature('VIX75', 'HMM_confidence', {'bull': 0.8, 'bear': 0.1})
    print(store.get_all_features('VIX75'))