#
# Copyright (c) 2019-2020 SRI International.
# All rights reserved.
#

# Try to find the PBC librairies
# PBC_FOUND - system has PBC lib
# PBC_INCLUDE_DIRS - the PBC include directory
# PBC_LIBRARIES - Libraries needed to use PBC

if (PBC_INCLUDE_DIRS AND PBC_LIBRARIES)
        # Already in cache, be silent
        set(PBC_FIND_QUIETLY TRUE)
endif (PBC_INCLUDE_DIRS AND PBC_LIBRARIES)

find_path(PBC_INCLUDE_DIRS NAMES pbc.h
    HINTS $ENV{PBC_INC} pbc
    PATH_SUFFIXES pbc)
find_library(PBC_LIBRARIES NAMES pbc libpbc
    HINTS $ENV{PBC_LIB})

include(FindPackageHandleStandardArgs)
FIND_PACKAGE_HANDLE_STANDARD_ARGS(PBC DEFAULT_MSG PBC_INCLUDE_DIRS PBC_LIBRARIES)

mark_as_advanced(PBC_INCLUDE_DIRS PBC_LIBRARIES)