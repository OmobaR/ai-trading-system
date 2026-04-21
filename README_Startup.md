## ✅ **Daily Startup Checklist (After PC Reboot)**

Follow these steps every time you restart your computer to avoid connection errors and missing modules.

---

### **1. Start Docker Desktop**
- Launch Docker Desktop from the Start menu.
- Wait for the Docker engine to start (whale icon becomes steady).

### **2. Open PowerShell (as Administrator – optional but recommended)**
- Press `Win + X`, select **Windows Terminal** or **PowerShell**.

### **3. Navigate to your project folder**
```powershell
cd C:\Users\Olugb\Workspace\ai-trading-system
```

### **4. Activate the Python virtual environment**
```powershell
.\ai_trading_env\Scripts\Activate.ps1
```
You should see `(ai_trading_env)` in the prompt.

### **5. Start the database and Redis containers**
```powershell
docker-compose -f docker/compose/docker-compose.dev.yml up -d
```
Wait 10–15 seconds for containers to become healthy. Check with:
```powershell
docker ps
```
You should see `ai_trading_timescaledb` and `ai_trading_redis` with status `healthy`.

### **6. Verify database connectivity**
```powershell
docker exec -e PGPASSWORD=password ai_trading_timescaledb psql -U postgres -d ai_trading_db -c "SELECT 1;"
```
If you see `1`, the database is ready.

### **7. Set environment variables (optional – your `.env` file already contains these)**
If you ever need to override, run:
```powershell
$env:DB_HOST="localhost"
$env:REDIS_HOST="localhost"
$env:MODE="simulate"
```
But normally your `.env` file is loaded automatically by `settings.py`.

### **8. Run your desired script**
- **Simulation (live trading simulation):**
  ```powershell
  python src/main.py --mode simulate
  ```
- **Backtest (SAE strategy):**
  ```powershell
  python scripts/run_sae_backtest.py
  ```
- **Parameter optimisation:**
  ```powershell
  python scripts/optimize_sae.py
  ```
- **Health check (in another terminal):**
  ```powershell
  curl http://localhost:8080/health
  ```

---

## 🛑 **Troubleshooting Common Startup Errors**

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'dotenv'` | Your virtual environment is not activated. Run step 4. |
| `Connection refused` (PostgreSQL) | Docker containers not running. Run step 5. |
| `psql: command not found` | You are in PowerShell; use `docker exec ...` as shown in step 6. |
| `Port 5432 already in use` | Another PostgreSQL instance is running. Stop it or change port in `.env`. |
| `Cannot connect to Redis` | Ensure Redis container is healthy (`docker ps`). |

---

## 🚀 **Pro Tip: Create a Startup Script**

Save the following as `start_trading.bat` in your project folder:

```batch
@echo off
cd /d C:\Users\Olugb\Workspace\ai-trading-system
call ai_trading_env\Scripts\activate.bat
docker-compose -f docker/compose/docker-compose.dev.yml up -d
echo Waiting for databases...
timeout /t 10
python src/main.py --mode simulate
pause
```

Double‑click the batch file after Docker Desktop is running.

---

## 📌 **Now Proceed**

After following the checklist, run the optimisation on `FX Vol 99`:

```powershell
python scripts/optimize_sae.py
```

Let me know the results. If still zero return, we will adjust the SAE strategy or try a different symbol.





===== BEST FOR CATEGORY =====
category     synthetics
symbol        PainX 999
window               20
threshold           0.5
return         0.001857
sharpe        39.661714
trades                9
signals               9
max_dd              0.0
Name: 128, dtype: object



===== BEST FOR CATEGORY =====
category     volatility
symbol       SFX Vol 99
window               20
threshold           2.0
return        -0.006023
sharpe        -0.040935
trades             8610
signals            8610
max_dd         0.015658
Name: 147, dtype: objec



===== BEST FOR CATEGORY =====
category            trend
symbol       SwitchX 1800
window                 20
threshold             2.0
return           0.001232
sharpe          26.443596
trades                 15
signals                15
max_dd           0.000073
Name: 83, dtype: object



===== BEST FOR CATEGORY =====
category        breakout
symbol       BreakX 1800
window                20
threshold            2.0
return          0.000371
sharpe          13.33598
trades                 5
signals                5
max_dd          0.000073
Name: 35, dtype: object


===== GLOBAL SUMMARY =====
              return     sharpe       trades
category
breakout   -0.000149 -10.125123     3.500000
synthetics -0.001418 -12.654845    12.300000
trend      -0.001025 -30.806881     7.958333
volatility -0.018727  -2.887810  4120.975000

===== BEST GLOBAL CONFIG =====
       category      symbol  window  threshold    return     sharpe  trades  signals    max_dd
128  synthetics   PainX 999      20        0.5  0.001857  39.661714       9        9  0.000000
128  volatility  SFX Vol 80      20        0.5 -0.012027  -0.655283    2538     2538  0.013077
(ai_trading_env) PS C:\Users\Olugb\Workspace\ai-trading-system>