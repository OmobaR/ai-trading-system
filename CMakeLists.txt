# CMakeLists.txt for building the bridge DLL
cmake_minimum_required(VERSION 3.15)
project(AITradingBridge)

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Python configuration
find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)

# Pybind11 configuration
find_package(pybind11 REQUIRED)

# Create shared library
pybind11_add_module(bridge_dll SHARED 
    src/execution/bridge_dll.cpp
)

# Set output name and location
set_target_properties(bridge_dll PROPERTIES
    OUTPUT_NAME "bridge_dll"
    SUFFIX ".dll"
    PREFIX ""
)

# Installation (for development)
install(TARGETS bridge_dll
    DESTINATION ${CMAKE_BINARY_DIR}/dist
)

# Windows-specific settings
if(WIN32)
    target_compile_definitions(bridge_dll PRIVATE 
        UNICODE 
        _UNICODE
    )
    
    target_link_libraries(bridge_dll PRIVATE
        pybind11::embed
    )
endif()

# Copy to MQL5 Libraries directory (adjust path as needed)
add_custom_command(TARGET bridge_dll POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy
        ${CMAKE_BINARY_DIR}/dist/bridge_dll.dll
        "C:/Users/olugb/AppData/Roaming/MetaQuotes/Terminal/DEV_ID/MQL5/Libraries/bridge_dll.dll"
    COMMENT "Copying DLL to MT5 Libraries directory"
)