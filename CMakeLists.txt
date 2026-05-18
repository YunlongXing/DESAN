cmake_minimum_required(VERSION 3.20)

if(UNIX AND NOT APPLE)
  find_program(DESAN_BOOTSTRAP_GXX g++)
  if(DESAN_BOOTSTRAP_GXX)
    execute_process(
      COMMAND ${DESAN_BOOTSTRAP_GXX} -dumpversion
      OUTPUT_VARIABLE DESAN_BOOTSTRAP_GXX_VERSION
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    execute_process(
      COMMAND ${DESAN_BOOTSTRAP_GXX} -dumpmachine
      OUTPUT_VARIABLE DESAN_BOOTSTRAP_GXX_TRIPLE
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )

    set(DESAN_BOOTSTRAP_STDLIB_LIBDIR
      /usr/lib/gcc/${DESAN_BOOTSTRAP_GXX_TRIPLE}/${DESAN_BOOTSTRAP_GXX_VERSION}
    )
    if(EXISTS "${DESAN_BOOTSTRAP_STDLIB_LIBDIR}")
      set(CMAKE_EXE_LINKER_FLAGS_INIT
        "${CMAKE_EXE_LINKER_FLAGS_INIT} -L${DESAN_BOOTSTRAP_STDLIB_LIBDIR}"
      )
      set(CMAKE_SHARED_LINKER_FLAGS_INIT
        "${CMAKE_SHARED_LINKER_FLAGS_INIT} -L${DESAN_BOOTSTRAP_STDLIB_LIBDIR}"
      )
      set(CMAKE_MODULE_LINKER_FLAGS_INIT
        "${CMAKE_MODULE_LINKER_FLAGS_INIT} -L${DESAN_BOOTSTRAP_STDLIB_LIBDIR}"
      )
    endif()
  endif()
endif()

project(DESAN LANGUAGES CXX)

find_package(LLVM REQUIRED CONFIG)

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

include_directories(${LLVM_INCLUDE_DIRS})
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/include)
add_definitions(${LLVM_DEFINITIONS})

add_library(DESANPass MODULE
  lib/DESANPass.cpp
  lib/LLMAssistedAnalyzer.cpp
  lib/RedundantCheckEliminator.cpp
  lib/CheckSliceRemover.cpp
  lib/CheckGraphBuilder.cpp
  lib/CheckedVariableAnalyzer.cpp
  lib/SanitizerCheckCollector.cpp
)

if(CMAKE_CXX_COMPILER_ID MATCHES "Clang" AND UNIX AND NOT APPLE)
  find_program(DESAN_GXX g++)
  if(DESAN_GXX)
    execute_process(
      COMMAND ${DESAN_GXX} -dumpversion
      OUTPUT_VARIABLE DESAN_GXX_VERSION
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    execute_process(
      COMMAND ${DESAN_GXX} -dumpmachine
      OUTPUT_VARIABLE DESAN_GXX_TRIPLE
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )

    set(DESAN_CXX_STDLIB_INCLUDE_DIRS
      /usr/include/c++/${DESAN_GXX_VERSION}
      /usr/include/${DESAN_GXX_TRIPLE}/c++/${DESAN_GXX_VERSION}
      /usr/include/c++/${DESAN_GXX_VERSION}/backward
      /usr/lib/gcc/${DESAN_GXX_TRIPLE}/${DESAN_GXX_VERSION}/include
    )
    set(DESAN_CXX_STDLIB_LIBRARY_DIRS
      /usr/lib/gcc/${DESAN_GXX_TRIPLE}/${DESAN_GXX_VERSION}
    )

    foreach(DESAN_INCLUDE_DIR IN LISTS DESAN_CXX_STDLIB_INCLUDE_DIRS)
      if(EXISTS "${DESAN_INCLUDE_DIR}")
        target_include_directories(DESANPass SYSTEM PRIVATE
          "${DESAN_INCLUDE_DIR}"
        )
        message(STATUS "Adding C++ standard library include: ${DESAN_INCLUDE_DIR}")
      endif()
    endforeach()

    foreach(DESAN_LIBRARY_DIR IN LISTS DESAN_CXX_STDLIB_LIBRARY_DIRS)
      if(EXISTS "${DESAN_LIBRARY_DIR}")
        target_link_directories(DESANPass PRIVATE "${DESAN_LIBRARY_DIR}")
        message(STATUS "Adding C++ standard library libdir: ${DESAN_LIBRARY_DIR}")
      endif()
    endforeach()
  endif()
endif()

set_target_properties(DESANPass PROPERTIES
  PREFIX ""
)

if(APPLE)
  set_target_properties(DESANPass PROPERTIES
    LINK_FLAGS "-Wl,-undefined,dynamic_lookup"
  )
else()
  if(LLVM_LINK_LLVM_DYLIB)
    target_link_libraries(DESANPass PRIVATE LLVM)
  else()
    llvm_map_components_to_libnames(LLVM_LIBS Core Support Passes)
    target_link_libraries(DESANPass PRIVATE ${LLVM_LIBS})
  endif()
endif()
