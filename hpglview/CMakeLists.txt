cmake_minimum_required(VERSION 3.16)
project(hpglview CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()
add_compile_options(-Wall -Wextra)

# parser: no Qt, so the tests build anywhere
add_library(hpgl STATIC hpgl.cpp)
target_include_directories(hpgl PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

enable_testing()
add_executable(test_hpgl tests/test_hpgl.cpp)
target_link_libraries(test_hpgl hpgl)
target_compile_definitions(test_hpgl PRIVATE DATA_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/data")
add_test(NAME hpgl COMMAND test_hpgl)

find_package(Qt6 COMPONENTS Core Gui Widgets QUIET)
if(Qt6_FOUND)
    set(CMAKE_AUTOMOC ON)
    add_executable(hpglview main.cpp view.cpp)
    target_link_libraries(hpglview hpgl Qt6::Core Qt6::Gui Qt6::Widgets)
    # Terminus from pcbooker's fonts/, for the status line and the PNG summary
    qt_add_resources(hpglview fonts
        PREFIX /fonts
        BASE ${CMAKE_CURRENT_SOURCE_DIR}/../fonts
        FILES ${CMAKE_CURRENT_SOURCE_DIR}/../fonts/Terminus.ttf
              ${CMAKE_CURRENT_SOURCE_DIR}/../fonts/TerminusBold.ttf)
else()
    message(STATUS "Qt6 not found: building the parser and tests only")
endif()
