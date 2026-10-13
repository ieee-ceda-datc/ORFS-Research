cmake_minimum_required(VERSION 3.14)

project(Differentiable3DPartitioner NONE)

option(D3D_BUILD_NESTED_DREAMPLACE "Build Differentiable-3D-Partitioner bundled DREAMPlace. D2D normally reuses the top-level DREAMPlace build." OFF)

if(D3D_BUILD_NESTED_DREAMPLACE)
  include(ExternalProject)
endif()

set(D3D_PARTITIONER_INSTALL_DEST thirdparty/Differentiable-3D-Partitioner)
set(D3D_DREAMPLACE_SOURCE_DIR
    ${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/DREAMPlace)
set(D3D_DREAMPLACE_BINARY_DIR
    ${CMAKE_CURRENT_BINARY_DIR}/thirdparty/DREAMPlace-build)
set(D3D_DREAMPLACE_INSTALL_DIR
    ${CMAKE_CURRENT_BINARY_DIR}/thirdparty/DREAMPlace-install)
set(D3D_DREAMPLACE_BUILD_RUNTIME_SCRIPT
    ${CMAKE_CURRENT_BINARY_DIR}/build_dreamplace_runtime.cmake)
set(D3D_DREAMPLACE_INSTALL_RUNTIME_SCRIPT
    ${CMAKE_CURRENT_BINARY_DIR}/install_dreamplace_runtime.cmake)

if(D3D_BUILD_NESTED_DREAMPLACE AND NOT EXISTS ${D3D_DREAMPLACE_SOURCE_DIR}/CMakeLists.txt)
  message(FATAL_ERROR
    "Differentiable-3D-Partitioner DREAMPlace submodule is missing. "
    "Run `git submodule update --init --recursive` from the D2D-placer "
    "repository root.")
endif()

file(MAKE_DIRECTORY ${D3D_DREAMPLACE_INSTALL_DIR})

set(D3D_DREAMPLACE_CMAKE_ARGS
    -DCMAKE_INSTALL_PREFIX=${D3D_DREAMPLACE_INSTALL_DIR}
    -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
    -DCMAKE_CXX_ABI=${CMAKE_CXX_ABI}
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    -DCUDA_USE_STATIC_CUDA_RUNTIME=OFF
    -DCUDA_PROPAGATE_HOST_FLAGS=ON
    -UCOIN_*
    -ULEMON_DEFAULT_*
    -DLEMON_ENABLE_COIN=NO)

if(CMAKE_CXX_COMPILER)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       -DCMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER})
endif()

if(CMAKE_C_COMPILER)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER})
endif()

if(Python_EXECUTABLE)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       -DPython_EXECUTABLE=${Python_EXECUTABLE}
       -DPYTHON_EXECUTABLE=${Python_EXECUTABLE})
elseif(PYTHON_EXECUTABLE)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       -DPYTHON_EXECUTABLE=${PYTHON_EXECUTABLE})
endif()

if(CMAKE_PREFIX_PATH)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       -DCMAKE_PREFIX_PATH=${CMAKE_PREFIX_PATH})
endif()

if(CUDA_TOOLKIT_ROOT_DIR)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       -DCUDA_TOOLKIT_ROOT_DIR=${CUDA_TOOLKIT_ROOT_DIR})
endif()

if(CUDA_NVCC_EXECUTABLE)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       -DCUDA_NVCC_EXECUTABLE=${CUDA_NVCC_EXECUTABLE})
endif()

if(CMAKE_CUDA_ARCHITECTURES)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       -DCMAKE_CUDA_ARCHITECTURES=${CMAKE_CUDA_ARCHITECTURES})
endif()

foreach(D3D_FORWARDED_CACHE_VAR
        BOOST_ROOT
        Boost_INCLUDE_DIR
        Boost_LIBRARY_DIR_DEBUG
        Boost_LIBRARY_DIR_RELEASE
        Boost_GRAPH_LIBRARY_DEBUG
        Boost_GRAPH_LIBRARY_RELEASE
        Boost_REGEX_LIBRARY_DEBUG
        Boost_REGEX_LIBRARY_RELEASE
        BISON_EXECUTABLE
        FLEX_EXECUTABLE
        FLEX_INCLUDE_DIR
        ZLIB_ROOT
        ZLIB_INCLUDE_DIR
        ZLIB_LIBRARY)
  if(DEFINED ${D3D_FORWARDED_CACHE_VAR})
    list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
         -D${D3D_FORWARDED_CACHE_VAR}=${${D3D_FORWARDED_CACHE_VAR}})
  endif()
endforeach()

if(D3D_BUILD_NESTED_DREAMPLACE)
if(ZLIB_INCLUDE_DIR)
  list(APPEND D3D_DREAMPLACE_CMAKE_ARGS
       "-DCMAKE_C_FLAGS=${CMAKE_C_FLAGS} -I${ZLIB_INCLUDE_DIR}"
       "-DCMAKE_CXX_FLAGS=${CMAKE_CXX_FLAGS} -I${ZLIB_INCLUDE_DIR}")
endif()

set(D3D_DREAMPLACE_RUNTIME_TARGETS
    place_io_cpp
    dct_cpp
    dct_lee_cpp
    dct2_fft2_cpp
    dct_cuda
    dct_lee_cuda
    dct2_fft2_cuda
    pin_pos_cpp
    pin_pos_cuda
    pin_pos_cuda_segment
    move_boundary_cpp
    move_boundary_cuda
    draw_place_cpp
    density_map_cpp
    density_map_cuda
    density_potential_cpp
    density_potential_cuda
    electric_potential_cpp
    electric_potential_cuda
    hpwl_cpp
    hpwl_cpp_atomic
    hpwl_cuda
    hpwl_cuda_atomic
    weighted_average_wirelength_cpp
    weighted_average_wirelength_cpp_atomic
    weighted_average_wirelength_cpp_merged
    weighted_average_wirelength_cuda
    weighted_average_wirelength_cuda_atomic
    weighted_average_wirelength_cuda_merged
    logsumexp_wirelength_cpp_merged
    logsumexp_wirelength_cuda_merged
    logsumexp_wirelength_cuda_atomic
    legality_check_cpp
    macro_legalize_cpp
    greedy_legalize_cpp
    abacus_legalize_cpp
    global_swap_cpp
    global_swap_concurrent_cpp
    global_swap_cuda
    independent_set_matching_cpp
    independent_set_matching_sequential_cpp
    independent_set_matching_cuda
    k_reorder_cpp
    k_reorder_cuda
    pin_utilization_cpp
    pin_utilization_cuda
    rudy_cpp
    rudy_cuda
    pinrudy_cpp
    pinrudy_cuda
    adjust_node_area_cpp
    update_pin_offset_cpp
    adjust_node_area_cuda
    update_pin_offset_cuda
    pws_cpp
    pws_cuda
    timing_cpp
    gift_init_cpp)

set(D3D_DREAMPLACE_RUNTIME_TARGET_LINES "")
foreach(D3D_DREAMPLACE_RUNTIME_TARGET IN LISTS D3D_DREAMPLACE_RUNTIME_TARGETS)
  string(APPEND D3D_DREAMPLACE_RUNTIME_TARGET_LINES
         "list(APPEND D3D_DREAMPLACE_RUNTIME_TARGETS \"${D3D_DREAMPLACE_RUNTIME_TARGET}\")\n")
endforeach()

file(WRITE ${D3D_DREAMPLACE_BUILD_RUNTIME_SCRIPT}
"set(D3D_DREAMPLACE_BINARY_DIR \"${D3D_DREAMPLACE_BINARY_DIR}\")\n"
"${D3D_DREAMPLACE_RUNTIME_TARGET_LINES}"
"execute_process(\n"
"  COMMAND \"${CMAKE_COMMAND}\" --build \"${D3D_DREAMPLACE_BINARY_DIR}\" --target help\n"
"  OUTPUT_VARIABLE D3D_DREAMPLACE_TARGET_HELP\n"
"  RESULT_VARIABLE D3D_DREAMPLACE_HELP_RESULT)\n"
"if(NOT D3D_DREAMPLACE_HELP_RESULT EQUAL 0)\n"
"  message(FATAL_ERROR \"Failed to query DREAMPlace build targets\")\n"
"endif()\n"
"set(D3D_DREAMPLACE_AVAILABLE_TARGETS)\n"
"foreach(D3D_DREAMPLACE_TARGET IN LISTS D3D_DREAMPLACE_RUNTIME_TARGETS)\n"
"  if(D3D_DREAMPLACE_TARGET_HELP MATCHES \"(^|[\\r\\n])\\\\.\\\\.\\\\. \${D3D_DREAMPLACE_TARGET}([\\r\\n]|$)\")\n"
"    list(APPEND D3D_DREAMPLACE_AVAILABLE_TARGETS \"\${D3D_DREAMPLACE_TARGET}\")\n"
"  endif()\n"
"endforeach()\n"
"if(NOT D3D_DREAMPLACE_AVAILABLE_TARGETS)\n"
"  message(FATAL_ERROR \"No DREAMPlace runtime targets are available\")\n"
"endif()\n"
"execute_process(\n"
"  COMMAND \"${CMAKE_COMMAND}\" --build \"${D3D_DREAMPLACE_BINARY_DIR}\" --parallel --target \${D3D_DREAMPLACE_AVAILABLE_TARGETS}\n"
"  RESULT_VARIABLE D3D_DREAMPLACE_BUILD_RESULT)\n"
"if(NOT D3D_DREAMPLACE_BUILD_RESULT EQUAL 0)\n"
"  message(FATAL_ERROR \"Failed to build DREAMPlace runtime targets\")\n"
"endif()\n")

file(WRITE ${D3D_DREAMPLACE_INSTALL_RUNTIME_SCRIPT}
"set(D3D_DREAMPLACE_SOURCE_DIR \"${D3D_DREAMPLACE_SOURCE_DIR}\")\n"
"set(D3D_DREAMPLACE_BINARY_DIR \"${D3D_DREAMPLACE_BINARY_DIR}\")\n"
"set(D3D_DREAMPLACE_INSTALL_DIR \"${D3D_DREAMPLACE_INSTALL_DIR}\")\n"
"file(REMOVE_RECURSE \"${D3D_DREAMPLACE_INSTALL_DIR}/dreamplace\")\n"
"file(MAKE_DIRECTORY \"${D3D_DREAMPLACE_INSTALL_DIR}\")\n"
"file(COPY \"${D3D_DREAMPLACE_SOURCE_DIR}/dreamplace\"\n"
"     DESTINATION \"${D3D_DREAMPLACE_INSTALL_DIR}\"\n"
"     PATTERN \"__pycache__\" EXCLUDE\n"
"     PATTERN \"*.pyc\" EXCLUDE\n"
"     PATTERN \"*.so\" EXCLUDE)\n"
"file(COPY \"${D3D_DREAMPLACE_BINARY_DIR}/dreamplace/configure.py\"\n"
"     DESTINATION \"${D3D_DREAMPLACE_INSTALL_DIR}/dreamplace\")\n"
"if(EXISTS \"${D3D_DREAMPLACE_SOURCE_DIR}/thirdparty/NCTUgr.ICCAD2012\")\n"
"  file(MAKE_DIRECTORY \"${D3D_DREAMPLACE_INSTALL_DIR}/thirdparty\")\n"
"  file(COPY \"${D3D_DREAMPLACE_SOURCE_DIR}/thirdparty/NCTUgr.ICCAD2012\"\n"
"       DESTINATION \"${D3D_DREAMPLACE_INSTALL_DIR}/thirdparty\")\n"
"endif()\n"
"file(GLOB_RECURSE D3D_DREAMPLACE_EXTENSIONS\n"
"     \"${D3D_DREAMPLACE_BINARY_DIR}/dreamplace/ops/*.so\")\n"
"foreach(D3D_DREAMPLACE_EXTENSION IN LISTS D3D_DREAMPLACE_EXTENSIONS)\n"
"  if(D3D_DREAMPLACE_EXTENSION MATCHES \"/timing_heterosta/\")\n"
"    continue()\n"
"  endif()\n"
"  file(RELATIVE_PATH D3D_DREAMPLACE_EXTENSION_REL\n"
"       \"${D3D_DREAMPLACE_BINARY_DIR}/dreamplace\"\n"
"       \"\${D3D_DREAMPLACE_EXTENSION}\")\n"
"  get_filename_component(D3D_DREAMPLACE_EXTENSION_DIR\n"
"       \"\${D3D_DREAMPLACE_EXTENSION_REL}\" DIRECTORY)\n"
"  file(MAKE_DIRECTORY\n"
"       \"${D3D_DREAMPLACE_INSTALL_DIR}/dreamplace/\${D3D_DREAMPLACE_EXTENSION_DIR}\")\n"
"  file(COPY \"\${D3D_DREAMPLACE_EXTENSION}\"\n"
"       DESTINATION\n"
"       \"${D3D_DREAMPLACE_INSTALL_DIR}/dreamplace/\${D3D_DREAMPLACE_EXTENSION_DIR}\")\n"
"endforeach()\n")

ExternalProject_Add(differentiable_3d_partitioner_dreamplace
  SOURCE_DIR ${D3D_DREAMPLACE_SOURCE_DIR}
  BINARY_DIR ${D3D_DREAMPLACE_BINARY_DIR}
  INSTALL_DIR ${D3D_DREAMPLACE_INSTALL_DIR}
  CMAKE_ARGS ${D3D_DREAMPLACE_CMAKE_ARGS}
  BUILD_COMMAND ${CMAKE_COMMAND} -P ${D3D_DREAMPLACE_BUILD_RUNTIME_SCRIPT}
  INSTALL_COMMAND ${CMAKE_COMMAND} -P ${D3D_DREAMPLACE_INSTALL_RUNTIME_SCRIPT}
  BUILD_ALWAYS OFF
  USES_TERMINAL_CONFIGURE TRUE
  USES_TERMINAL_BUILD TRUE
  USES_TERMINAL_INSTALL TRUE)
endif()

install(
  DIRECTORY partitioner configs examples tests
  DESTINATION ${D3D_PARTITIONER_INSTALL_DEST}
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
  PATTERN "*.so" EXCLUDE)

install(
  FILES README.md QUICKSTART.md LICENSE requirements.txt setup.py .gitmodules
  DESTINATION ${D3D_PARTITIONER_INSTALL_DEST}
  OPTIONAL)

if(D3D_BUILD_NESTED_DREAMPLACE)
  install(CODE
    "file(REMOVE_RECURSE \"${CMAKE_INSTALL_PREFIX}/${D3D_PARTITIONER_INSTALL_DEST}/thirdparty/DREAMPlace/install\")")

  install(
    DIRECTORY ${D3D_DREAMPLACE_INSTALL_DIR}/
    DESTINATION ${D3D_PARTITIONER_INSTALL_DEST}/thirdparty/DREAMPlace/install
    PATTERN "__pycache__" EXCLUDE
    PATTERN "*.pyc" EXCLUDE)
endif()
