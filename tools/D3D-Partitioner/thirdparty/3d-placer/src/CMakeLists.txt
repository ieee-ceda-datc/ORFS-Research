
# add_subdirectory(dataModel)
# add_subdirectory(main)
# add_subdirectory(parser)
# add_subdirectory(partitioner)
# add_subdirectory(placer)
# add_subdirectory(utility)

set(LIB_SOURCES
    parser/parser.cpp
    dataModel/dm.cpp
    dataModel/module.cpp
    dataModel/bin.cpp
    utility/paramHdl.cpp
    utility/message.cpp
    utility/drawHtml.cpp
    utility/aux.cpp
    utility/hgr.cpp
    placer/placer.cpp
    partitioner/partitioner.cpp
)

add_library(3d_placer_lib STATIC ${LIB_SOURCES})

# set include
target_include_directories(3d_placer_lib
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
        $<INSTALL_INTERFACE:include>
)

# set link libraries
target_link_libraries(3d_placer_lib PUBLIC
    m
    pthread
)

# install headers
# install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
#     DESTINATION src/ops/include
#     FILES_MATCHING PATTERN "*.h"
# )