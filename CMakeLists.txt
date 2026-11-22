cmake_minimum_required(VERSION 3.15...3.27)
project(pabo LANGUAGES CXX)
if(NOT SKBUILD)
  message(
    WARNING
      "\
  This CMake file is meant to be executed using 'scikit-build-core'.
  Running it directly will almost certainly not produce the desired
  result. If you are a user trying to install this package, use the
  command below, which will install all necessary build dependencies,
  compile the package in an isolated environment, and then install it.
  =====================================================================
   $ pip install .
  =====================================================================
  If you are a software developer, and this is your own package, then
  it is usually much more efficient to install the build dependencies
  in your environment once and use the following command that avoids
  a costly creation of a new virtual environment at every compilation:
  =====================================================================
   $ pip install nanobind scikit-build-core[pyproject]
   $ pip install --no-build-isolation -ve .
  =====================================================================
  You may optionally add -Ceditable.rebuild=true to auto-rebuild when
  the package is imported. Otherwise, you need to rerun the above
  after editing C++ files.")
endif()
find_package(
  Python 3.10 REQUIRED
  COMPONENTS Interpreter Development.Module
  OPTIONAL_COMPONENTS Development.SABIModule)
find_package(nanobind CONFIG REQUIRED)
nanobind_add_module(packed LTO NOMINSIZE STABLE_ABI src/pabo/packed.cpp)
find_package(OpenMP COMPONENTS CXX)
if(OpenMP_CXX_FOUND)
  target_link_libraries(packed PRIVATE OpenMP::OpenMP_CXX)
  target_compile_definitions(packed PRIVATE USE_OPENMP)
endif()
install(TARGETS packed LIBRARY DESTINATION pabo)
