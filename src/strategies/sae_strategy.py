# src/strategies/sae_strategy.py
"""
SAE strategy using reconstruction error as signal.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from src.strategies.base_strategy import BaseStrategy

class SAEStrategy(BaseStrategy):
    def __init__(self, symbol: str, window: int = 60, threshold: float = 1.5, **kwargs):
        super().__init__(symbol, **kwargs)
        self.window = window
        self.threshold = threshold
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=0.95)

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # Compute returns and features
        df['ret1'] = df['close'].pct_change()
        df['ret5'] = df['close'].pct_change(5)
        df['ret10'] = df['close'].pct_change(10)
        df['volatility'] = df['ret1'].rolling(20).std()
        df['volume_norm'] = df['volume'] / df['volume'].rolling(100).mean()
        
        # Features for PCA
        feature_cols = ['ret1', 'ret5', 'ret10', 'volatility', 'volume_norm']
        features = df[feature_cols].dropna().values
        
        if len(features) < self.window + 1:
            df['signal'] = 0
            return df

        # Compute rolling reconstruction error
        errors = []
        for i in range(self.window, len(features)):
            window_data = features[i-self.window:i]
            scaler = StandardScaler()
            pca = PCA(n_components=0.95)
            scaled = scaler.fit_transform(window_data)
            compressed = pca.fit_transform(scaled)
            reconstructed = pca.inverse_transform(compressed)
            # Reconstruction error of the last point in window
            last_recon_error = np.mean((scaled[-1] - reconstructed[-1]) ** 2)
            errors.append(last_recon_error)
        
        # Align errors with DataFrame index (skip initial rows that had NaNs)
        # The first valid index in features corresponds to the first row without NaN in any feature column
        valid_start = df[feature_cols].dropna().index[0]
        # The errors correspond to rows starting from valid_start + self.window
        error_index = df.index[df.index >= valid_start][self.window:]
        if len(error_index) != len(errors):
            # Fallback: use iloc positions
            error_positions = range(self.window, self.window + len(errors))
            error_index = df.iloc[error_positions].index
        
        df['reconstruction_error'] = np.nan
        df.loc[error_index, 'reconstruction_error'] = errors
        
        # Standardize error
        df['error_zscore'] = (df['reconstruction_error'] - df['reconstruction_error'].mean()) / df['reconstruction_error'].std()
        
        # Generate signals
        df['signal'] = 0
        buy_condition = (df['error_zscore'] > self.threshold) & (df['ret1'] > 0) & (df['ret5'] > 0)
        # Sell when error returns to normal after being high (simplified)
        sell_condition = (df['error_zscore'] < 0.5) & (df['signal'].shift(1) == 1)
        
        df.loc[buy_condition, 'signal'] = 1
        df.loc[sell_condition, 'signal'] = -1
        df['signal'].fillna(0, inplace=True)
        return df

    def get_parameters(self):
        return {'window': self.window, 'threshold': self.threshold}