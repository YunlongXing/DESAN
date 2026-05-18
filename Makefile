LLVM_CONFIG ?= llvm-config
CXX ?= clang++
OPT ?= opt

BUILD_DIR := build
TARGET := $(BUILD_DIR)/DESANPass.so
SOURCES := lib/DESANPass.cpp lib/LLMAssistedAnalyzer.cpp lib/RedundantCheckEliminator.cpp lib/CheckSliceRemover.cpp lib/CheckGraphBuilder.cpp lib/CheckedVariableAnalyzer.cpp lib/SanitizerCheckCollector.cpp
OBJECTS := $(patsubst lib/%.cpp,$(BUILD_DIR)/%.o,$(SOURCES))
HEADERS := $(wildcard include/DESAN/*.h)

LLVM_CXXFLAGS = $(shell $(LLVM_CONFIG) --cxxflags)
LLVM_LDFLAGS = $(shell $(LLVM_CONFIG) --ldflags)
LLVM_LIBS = $(shell $(LLVM_CONFIG) --libs core support passes)
LLVM_SYSTEM_LIBS = $(shell $(LLVM_CONFIG) --system-libs)
GCC_CXX_INCLUDE_DIRS ?= $(shell if command -v g++ >/dev/null 2>&1; then \
	v=$$(g++ -dumpversion); \
	t=$$(g++ -dumpmachine); \
	for d in /usr/include/c++/$$v \
	         /usr/include/$$t/c++/$$v \
	         /usr/include/c++/$$v/backward \
	         /usr/lib/gcc/$$t/$$v/include; do \
	  [ -d "$$d" ] && printf '%s ' "$$d"; \
	done; \
fi)
CXX_STDLIB_CXXFLAGS ?= $(addprefix -isystem ,$(GCC_CXX_INCLUDE_DIRS))
GCC_CXX_LIB_DIRS ?= $(shell if command -v g++ >/dev/null 2>&1; then \
	v=$$(g++ -dumpversion); \
	t=$$(g++ -dumpmachine); \
	for d in /usr/lib/gcc/$$t/$$v; do \
	  [ -d "$$d" ] && printf '%s ' "$$d"; \
	done; \
fi)
CXX_STDLIB_LDFLAGS ?= $(addprefix -L,$(GCC_CXX_LIB_DIRS))

UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
  SHARED_FLAGS := -dynamiclib -Wl,-undefined,dynamic_lookup
else
  SHARED_FLAGS := -shared
endif

CXXFLAGS += -std=c++17 -fPIC -Iinclude $(CXX_STDLIB_CXXFLAGS) $(LLVM_CXXFLAGS)
LDFLAGS += $(CXX_STDLIB_LDFLAGS) $(LLVM_LDFLAGS)

.PHONY: all clean test

all: $(TARGET)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: lib/%.cpp $(HEADERS) | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) -c $< -o $@

$(TARGET): $(OBJECTS)
	$(CXX) $(SHARED_FLAGS) $(OBJECTS) $(LDFLAGS) $(LLVM_LIBS) $(LLVM_SYSTEM_LIBS) -o $@

test: $(TARGET)
	$(OPT) -load-pass-plugin=$(TARGET) -passes=desan-collect-checks -disable-output test/inputs/sanitizer_checks.ll

clean:
	rm -rf $(BUILD_DIR)
