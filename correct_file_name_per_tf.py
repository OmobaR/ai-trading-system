import os
import pandas as pd

folder = r"C:\Users\Olugb\Workspace\ai-trading-system\m1_m2_extracted"
for file in os.listdir(folder):
    if not file.endswith('_M1.csv'):
        continue
    filepath = os.path.join(folder, file)
    df = pd.read_csv(filepath, nrows=10)
    df['time'] = pd.to_datetime(df['time'])
    diffs = df['time'].diff().dropna()
    if len(diffs) == 0:
        continue
    median_sec = diffs.median().total_seconds()
    if 55 <= median_sec <= 65:
        new = file  # keep as M1
    elif 295 <= median_sec <= 305:
        new = file.replace('_M1.csv', '_M5.csv')
    else:
        # For other intervals (e.g., if you ever find M2), add more cases.
        continue
    if new != file:
        os.rename(filepath, os.path.join(folder, new))
        print(f"Renamed {file} -> {new}")