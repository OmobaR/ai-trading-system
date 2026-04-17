#!/usr/bin/env python3
"""
Generate equity curve and drawdown plots from backtest results.
"""

import argparse
import json
import matplotlib.pyplot as plt
import pandas as pd
import os

def plot_equity_curve(equity_curve_file, output_image='equity_curve.png'):
    with open(equity_curve_file, 'r') as f:
        data = json.load(f)
    # Expecting list of [timestamp, equity]
    df = pd.DataFrame(data, columns=['timestamp', 'equity'])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    plt.figure(figsize=(12, 6))
    plt.plot(df.index, df['equity'], label='Equity')
    plt.title('Equity Curve')
    plt.xlabel('Date')
    plt.ylabel('Equity')
    plt.legend()
    plt.grid(True)
    plt.savefig(output_image)
    plt.close()
    print(f"Saved equity curve to {output_image}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--equity', required=True, help='JSON file with equity curve')
    parser.add_argument('--output', default='equity_curve.png')
    args = parser.parse_args()
    plot_equity_curve(args.equity, args.output)