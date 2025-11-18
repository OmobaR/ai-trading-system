# For compiling the DLL
cmake_minimum_required(VERSION 3.15)
project(bridge_dll)

find_package(pybind11 REQUIRED)

add_library(bridge_dll SHARED src/execution/bridge_dll.cpp)
target_link_libraries(bridge_dll PRIVATE pybind11::embed)