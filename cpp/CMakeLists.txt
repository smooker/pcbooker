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

add_library(pcbook STATIC libpcbook/pcbook.cpp)
target_include_directories(pcbook PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/libpcbook
    ${CMAKE_CURRENT_SOURCE_DIR}/ext/json
    ${CMAKE_CURRENT_SOURCE_DIR}/ext/stb)
target_link_libraries(pcbook PUBLIC clipper2)

enable_testing()
add_executable(test_ext tests/test_ext.cpp)
target_link_libraries(test_ext pcbook)
add_test(NAME ext COMMAND test_ext)
