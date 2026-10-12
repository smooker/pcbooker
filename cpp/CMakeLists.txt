cmake_minimum_required(VERSION 3.16)
project(pcbook CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()

# --- third party, all in the repo (ext/README.md) ---
set(CLIPPER2_DIR ${CMAKE_CURRENT_SOURCE_DIR}/ext/Clipper2/CPP/Clipper2Lib)
if(NOT EXISTS ${CLIPPER2_DIR}/src/clipper.engine.cpp)
    message(FATAL_ERROR "ext/Clipper2 is empty: run `git submodule update --init` in the repo")
endif()
add_library(clipper2 STATIC
    ${CLIPPER2_DIR}/src/clipper.engine.cpp
    ${CLIPPER2_DIR}/src/clipper.offset.cpp
    ${CLIPPER2_DIR}/src/clipper.rectclip.cpp)
target_include_directories(clipper2 PUBLIC ${CLIPPER2_DIR}/include)

# --- our code: warnings on, after the third-party targets ---
add_compile_options(-Wall -Wextra)

add_library(pcbook STATIC libpcbook/pcbook.cpp libpcbook/hpgl.cpp)
target_include_directories(pcbook PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/libpcbook
    ${CMAKE_CURRENT_SOURCE_DIR}/ext/json
    ${CMAKE_CURRENT_SOURCE_DIR}/ext/stb)
target_link_libraries(pcbook PUBLIC clipper2)

enable_testing()
add_executable(test_ext tests/test_ext.cpp)
target_link_libraries(test_ext pcbook)
add_test(NAME ext COMMAND test_ext)

add_executable(test_hpgl tests/test_hpgl.cpp)
target_link_libraries(test_hpgl pcbook)
target_compile_definitions(test_hpgl PRIVATE DATA_DIR="${CMAKE_CURRENT_SOURCE_DIR}/tests/data")
add_test(NAME hpgl COMMAND test_hpgl)

# --- Qt6 front ends: optional, the chroot has no Qt ---
find_package(Qt6 COMPONENTS Core Gui Widgets QUIET)
if(Qt6_FOUND)
    set(CMAKE_AUTOMOC ON)
    add_executable(hpglview hpglview/main.cpp hpglview/view.cpp)
    target_link_libraries(hpglview pcbook Qt6::Core Qt6::Gui Qt6::Widgets)
    # Terminus from pcbooker's fonts/, for the status line and the PNG summary
    qt_add_resources(hpglview fonts
        PREFIX /fonts
        BASE ${CMAKE_CURRENT_SOURCE_DIR}/../fonts
        FILES ${CMAKE_CURRENT_SOURCE_DIR}/../fonts/Terminus.ttf
              ${CMAKE_CURRENT_SOURCE_DIR}/../fonts/TerminusBold.ttf)
else()
    message(STATUS "Qt6 not found: library, CLI, MCP and tests only")
endif()
