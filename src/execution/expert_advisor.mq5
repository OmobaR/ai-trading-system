# src/execution/expert_advisor.mq5
// MQL5 Expert Advisor as thin wrapper
// Calls DLL functions, handles execution with CTrade
// Includes reconnection logic for broker

#property copyright "xAI Trading System"
#property link      "https://x.ai"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

// DLL imports
#import "bridge_dll.dll"
bool InitBridge();
int GetTradeSignal(string symbol, double &volume, double &sl_points, double &tp_points);
void DeInitBridge();
#import

CTrade trade;
bool dllInitialized = false;
int reconnectAttempts = 0;
const int MAX_RECONNECT = 5;

// OnInit: Initialize DLL
int OnInit() {
    if (!InitBridge()) {
        Print("DLL initialization failed");
        return(INIT_FAILED);
    }
    dllInitialized = true;
    Print("DLL initialized successfully");
    return(INIT_SUCCEEDED);
}

// OnDeinit: Cleanup DLL
void OnDeinit(const int reason) {
    if (dllInitialized) {
        DeInitBridge();
        Print("DLL deinitialized");
    }
}

// OnTick: Get signal and execute
void OnTick() {
    if (!IsConnected()) {
        if (reconnectAttempts < MAX_RECONNECT) {
            Print("Broker disconnected, attempting reconnect...");
            reconnectAttempts++;
            // Reconnect logic (MT5 auto-reconnects, but add delay or reset)
            Sleep(1000);
            return;
        } else {
            Print("Max reconnect attempts reached. Stopping.");
            ExpertRemove();
            return;
        }
    }
    reconnectAttempts = 0;  // Reset on successful tick

    string sym = Symbol();
    double vol = 0.0, sl_points = 0.0, tp_points = 0.0;
    int signal_type = GetTradeSignal(sym, vol, sl_points, tp_points);

    if (signal_type == 1) {  // Example: BUY
        double entry = Ask;
        double sl_level = entry - sl_points * Point;
        double tp_level = entry + tp_points * Point;
        if (!trade.Buy(vol, sym, entry, sl_level, tp_level, "ML_Regime_Buy")) {
            Print("Buy order failed: ", GetLastError());
        } else {
            Print("Buy order executed");
        }
    } else if (signal_type == -1) {  // SELL
        double entry = Bid;
        double sl_level = entry + sl_points * Point;
        double tp_level = entry - tp_points * Point;
        if (!trade.Sell(vol, sym, entry, sl_level, tp_level, "ML_Regime_Sell")) {
            Print("Sell order failed: ", GetLastError());
        } else {
            Print("Sell order executed");
        }
    } else if (signal_type == -1) {  // Error
        Print("Signal retrieval failed");
    }
}