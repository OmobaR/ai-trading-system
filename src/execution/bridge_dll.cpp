// src/execution/bridge_dll.cpp
// C++ DLL for Python-MQL5 bridge using pybind11
// Enhanced with proper error handling and shared memory

#include <pybind11/embed.h>
#include <pybind11/stl.h>
#include <windows.h>
#include <string>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <sstream>

namespace py = pybind11;

// Global variables
static py::scoped_interpreter* interpreter = nullptr;
static HANDLE hMapFile = NULL;
static LPVOID pBuf = NULL;
const char* SHARED_MEM_NAME = "AITradingBridgeSharedMem";
const int BUF_SIZE = 4096;  // Increased buffer size

// Helper function to convert string to wstring
std::wstring string_to_wstring(const std::string& str) {
    if (str.empty()) return std::wstring();
    int size_needed = MultiByteToWideChar(CP_UTF8, 0, &str[0], (int)str.size(), NULL, 0);
    std::wstring wstrTo(size_needed, 0);
    MultiByteToWideChar(CP_UTF8, 0, &str[0], (int)str.size(), &wstrTo[0], size_needed);
    return wstrTo;
}

// DLL Export: Initialize the Python interpreter and shared memory
extern "C" __declspec(dllexport) bool InitBridge() {
    try {
        std::cout << "🚀 Initializing AI Trading Bridge..." << std::endl;
        
        // Initialize Python interpreter
        if (interpreter == nullptr) {
            // Set Python path to include the project directory
            std::string project_path = "C:/Users/olugb/ai-trading-system";
            std::wstring w_project_path = string_to_wstring(project_path);
            
            Py_SetPath(w_project_path.c_str());
            interpreter = new py::scoped_interpreter();
            
            std::cout << "✅ Python interpreter initialized" << std::endl;
        }

        // Create shared memory for high-frequency data
        hMapFile = CreateFileMapping(
            INVALID_HANDLE_VALUE,    // Use paging file
            NULL,                    // Default security
            PAGE_READWRITE,          // Read/write access
            0,                       // Maximum object size (high-order DWORD)
            BUF_SIZE,                // Maximum object size (low-order DWORD)
            SHARED_MEM_NAME);        // Name of mapping object

        if (hMapFile == NULL) {
            std::cerr << "❌ Could not create file mapping object: " << GetLastError() << std::endl;
            return false;
        }

        pBuf = MapViewOfFile(hMapFile,            // Handle to map object
                            FILE_MAP_ALL_ACCESS,  // Read/write permission
                            0,
                            0,
                            BUF_SIZE);

        if (pBuf == NULL) {
            std::cerr << "❌ Could not map view of file: " << GetLastError() << std::endl;
            CloseHandle(hMapFile);
            return false;
        }

        // Test Python functionality
        try {
            py::module_ sys = py::module_::import("sys");
            std::cout << "🐍 Python version: " << sys.attr("version").cast<std::string>() << std::endl;
            
            // Test import of signal_agent
            py::module_ signal_module = py::module_::import("src.execution.signal_agent");
            std::cout << "✅ Signal agent module loaded successfully" << std::endl;
            
        } catch (const py::error_already_set& e) {
            std::cerr << "❌ Python module test failed: " << e.what() << std::endl;
            return false;
        }

        std::cout << "✅ AI Trading Bridge initialized successfully" << std::endl;
        return true;

    } catch (const std::exception& e) {
        std::cerr << "❌ InitBridge error: " << e.what() << std::endl;
        return false;
    }
}

// DLL Export: Get trade signal from Python module
extern "C" __declspec(dllexport) int GetTradeSignal(const char* symbol, 
                                                   double* volume, 
                                                   double* sl_points, 
                                                   double* tp_points) {
    try {
        if (interpreter == nullptr) {
            std::cerr << "❌ Python interpreter not initialized" << std::endl;
            return -1;
        }

        // Import and call the signal agent
        py::module_ signal_module = py::module_::import("src.execution.signal_agent");
        py::object result = signal_module.attr("get_trade_signal")(symbol);

        // Extract results from dictionary
        int signal_type = result.attr("type").cast<int>();
        *volume = result.attr("volume").cast<double>();
        *sl_points = result.attr("sl").cast<double>();
        *tp_points = result.attr("tp").cast<double>();

        // Write to shared memory for monitoring
        std::stringstream ss;
        ss << "Signal:" << signal_type 
           << ",Symbol:" << symbol
           << ",Volume:" << *volume
           << ",SL:" << *sl_points
           << ",TP:" << *tp_points;
        
        std::string data_str = ss.str();
        if (pBuf && data_str.size() < BUF_SIZE) {
            CopyMemory(pBuf, data_str.c_str(), data_str.size() + 1);
        }

        std::cout << "📊 Generated signal for " << symbol 
                  << ": type=" << signal_type 
                  << ", volume=" << *volume 
                  << ", sl=" << *sl_points 
                  << ", tp=" << *tp_points << std::endl;

        return signal_type;

    } catch (const py::error_already_set& e) {
        std::cerr << "❌ Python error in GetTradeSignal: " << e.what() << std::endl;
        return -1;
    } catch (const std::exception& e) {
        std::cerr << "❌ GetTradeSignal error: " << e.what() << std::endl;
        return -1;
    }
}

// DLL Export: Get additional signal info as JSON string
extern "C" __declspec(dllexport) bool GetSignalDetails(const char* symbol, char* output, int output_size) {
    try {
        if (interpreter == nullptr) {
            return false;
        }

        py::module_ signal_module = py::module_::import("src.execution.signal_agent");
        py::object result = signal_module.attr("get_trade_signal")(symbol);
        
        // Convert to JSON string
        std::string json_str = py::str(result).cast<std::string>();
        
        if (json_str.size() < output_size) {
            strcpy_s(output, output_size, json_str.c_str());
            return true;
        }
        
        return false;

    } catch (...) {
        return false;
    }
}

// DLL Export: Cleanup interpreter and shared memory
extern "C" __declspec(dllexport) void DeInitBridge() {
    std::cout << "🛑 Deinitializing AI Trading Bridge..." << std::endl;
    
    if (pBuf) {
        UnmapViewOfFile(pBuf);
        pBuf = NULL;
    }
    
    if (hMapFile) {
        CloseHandle(hMapFile);
        hMapFile = NULL;
    }
    
    if (interpreter) {
        delete interpreter;
        interpreter = nullptr;
    }
    
    std::cout << "✅ AI Trading Bridge deinitialized" << std::endl;
}

// DLL Main
BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
        case DLL_PROCESS_ATTACH:
            std::cout << "🔧 DLL Process Attach" << std::endl;
            break;
        case DLL_PROCESS_DETACH:
            std::cout << "🔧 DLL Process Detach" << std::endl;
            DeInitBridge();
            break;
        case DLL_THREAD_ATTACH:
        case DLL_THREAD_DETACH:
            break;
    }
    return TRUE;
}