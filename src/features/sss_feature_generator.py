"""
Enhanced SSS Feature Generator v2
- Added pin_bar_score, breakout_score, trend_persistence
- Better normalization and regime detection
- Cleaner vectorized calculations
"""

import pandas as pd
import numpy as np
from typing import Dict

class SSSFeatureGenerator:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self._prepare_data()

    def _prepare_data(self):
        self.df['returns'] = self.df['close'].pct_change()
        self.df['atr_14'] = self._calculate_atr(14)
        self.df['atr_50'] = self._calculate_atr(50)
        self.df = self.df.dropna()

    def _calculate_atr(self, period: int) -> pd.Series:
        high_low = self.df['high'] - self.df['low']
        high_close = np.abs(self.df['high'] - self.df['close'].shift())
        low_close = np.abs(self.df['low'] - self.df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def generate_features(self) -> pd.DataFrame:
        df = self.df.copy()

        # Core momentum components
        df['bias'] = np.sign(df['close'] - df['close'].rolling(20).mean())
        df['velocity'] = df['returns'].rolling(10).mean() * 100
        df['trend_strength'] = abs(df['close'] - df['close'].rolling(50).mean()) / df['atr_14'].replace(0, np.nan)

        # Market regime
        vol_ratio = df['atr_14'] / df['atr_50'].replace(0, np.nan)
        df['state'] = np.where(vol_ratio > 1.35, 'volatile',
                              np.where(vol_ratio < 0.65, 'quiet', 'normal'))

        # Pin-bar score (strong reversal candle proxy)
        body = abs(df['close'] - df['open'])
        upper_wick = df['high'] - df[['open', 'close']].max(axis=1)
        lower_wick = df[['open', 'close']].min(axis=1) - df['low']
        df['pin_bar_score'] = np.where(body > 0, 
                                      np.maximum(upper_wick / body, lower_wick / body), 0).clip(0, 4)

        # Breakout score (strong momentum candle)
        df['breakout_score'] = np.where(body > 0,
                                       (df['high'] - df['low']) / body, 0).clip(0, 3)

        # Trend persistence
        df['trend_persistence'] = (df['bias'] == df['bias'].shift(1)).rolling(8).mean() * 100

        # Structure score
        df['structure_score'] = (df['velocity'].abs() * 0.45 +
                                df['pin_bar_score'] * 12 +
                                df['breakout_score'] * 15)

        # Final Net Score (improved weighting)
        df['net_score'] = (
            0.32 * np.clip(df['velocity'] * 9, -60, 90) +
            0.24 * np.clip(df['trend_strength'] * 22, 0, 70) +
            0.22 * np.clip(df['structure_score'], 0, 80) +
            0.12 * df['trend_persistence'] +
            0.10 * np.where(df['state'] == 'normal', 55, 25)
        ).clip(0, 100)

        df = df.fillna(0)
        return df

    def get_summary(self) -> Dict:
        features = self.generate_features()
        return {
            'rows': len(features),
            'avg_net_score': float(features['net_score'].mean()),
            'bias_distribution': features['bias'].value_counts().to_dict(),
            'state_distribution': features['state'].value_counts().to_dict(),
            'signal_potential': float((features['net_score'] > 35).mean() * 100)
        }