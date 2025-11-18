# src/execution/bridge_dll.cpp
// C++ DLL source for the Python-MQL5 bridge using pybind11
// Compile with CMake as SHARED library, linking pybind11::embed
// Exports functions for MQL5 to call, embedding Python interpreter
// For sub-ms latency, direct function calls; shared memory added for potential large data (using Windows file mapping)

#include <pybind11/embed.h>
#include <pybind11/stl.h>
#include <windows.h>  // For shared memory (file mapping)
#include <string>
#include <iostream>
#include <stdexcept>

namespace py = pybind11;

static py::scoped_interpreter* interpreter = nullptr;
static HANDLE hMapFile = NULL;
static LPCTSTR pBuf = NULL;
const char* SHARED_MEM_NAME = "TradeSignalSharedMem";
const int BUF_SIZE = 1024;  // Example size for shared data

// DLL Export: Initialize the Python interpreter and shared memory
extern "C" __declspec(dllexport) bool InitBridge() {
    try {
        if (interpreter == nullptr) {
            interpreter = new py::scoped_interpreter();
        }

        // Create shared memory (Windows-specific)
        hMapFile = CreateFileMapping(
            INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, BUF_SIZE, SHARED_MEM_NAME);
        if (hMapFile == NULL) {
            throw std::runtime_error("Could not create file mapping object.");
        }
        pBuf = (LPTSTR) MapViewOfFile(hMapFile, FILE_MAP_ALL_ACCESS, 0, 0, BUF_SIZE);
        if (pBuf == NULL) {
            CloseHandle(hMapFile);
            throw std::runtime_error("Could not map view of file.");
        }

        return true;
    } catch (const std::exception& e) {
        std::cerr << "InitBridge error: " << e.what() << std::endl;
        return false;
    }
}

// DLL Export: Get trade signal from Python module (example: signal_agent.py)
// Writes result to shared memory for low-latency access if needed
extern "C" __declspec(dllexport) int GetTradeSignal(const char* symbol, double* volume, double* sl_points, double* tp_points) {
    try {
        if (interpreter == nullptr) {
            throw std::runtime_error("Interpreter not initialized.");
        }

        py::module_ signal_module = py::module_::import("signal_agent");
        py::object result = signal_module.attr("get_trade_signal")(symbol);

        // Assume result is a dict: {"type": int, "volume": float, "sl": float, "tp": float}
        int signal_type = result.attr("type").cast<int>();
        *volume = result.attr("volume").cast<double>();
        *sl_points = result.attr("sl").cast<double>();
        *tp_points = result.attr("tp").cast<double>();

        // Optional: Write to shared memory (e.g., serialized)
        std::string data = std::to_string(signal_type) + "," + std::to_string(*volume);
        CopyMemory((PVOID)pBuf, data.c_str(), data.size());

        return signal_type;
    } catch (const py::error_already_set& e) {
        std::cerr << "Python error: " << e.what() << std::endl;
        return -1;  // Error code
    } catch (const std::exception& e) {
        std::cerr << "GetTradeSignal error: " << e.what() << std::endl;
        return -1;
    }
}

// DLL Export: Cleanup interpreter and shared memory
extern "C" __declspec(dllexport) void DeInitBridge() {
    if (pBuf) {
        UnmapViewOfFile(pBuf);
    }
    if (hMapFile) {
        CloseHandle(hMapFile);
    }
    if (interpreter) {
        delete interpreter;
        interpreter = nullptr;
    }
}

// Error handling and reconnection: If init fails, MQL5 can retry