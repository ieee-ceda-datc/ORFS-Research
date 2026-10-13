cmake_minimum_required(VERSION 3.7.0)

project(3d-placer CXX)

set(CMAKE_INSTALL_PREFIX "${CMAKE_CURRENT_SOURCE_DIR}" CACHE PATH "Prefix prepended to install directories")
# set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_compile_options(
    -O3
    -fomit-frame-pointer
    -funroll-loops
    -ffast-math
    -funit-at-a-time
    -fPIC
    -pthread
)

add_definitions(-DNDEBUG)
add_definitions(-DPARSER_LP)
add_definitions(-DINVERSE_ACTIVE=INVERSE_LUSOL)
add_definitions(-DRoleIsExternalInvEngine)

add_subdirectory(src)

add_executable(3d-placer src/main/main.cpp)
target_link_libraries(3d-placer PRIVATE 3d_placer_lib)

