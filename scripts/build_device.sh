#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/activate.sh"
bash "$HET_PROJECT_ROOT/vortexint/install.sh"
# The public configuration directory owns the advanced SimX defaults.
if ! cmp -s "$SS_ROOT/config/simx.toml" "$VORTEX_HOME/VX_config.toml"; then
    cp "$SS_ROOT/config/simx.toml" "$VORTEX_HOME/VX_config.toml"
fi
"$AXI_PYTHON" "$SS_ROOT/scripts/prepare_vortex_llvm.py"
simx_flags=$("$AXI_PYTHON" "$SS_ROOT/scripts/configure.py" --simx-flags "$@")
read -ra benchmarks <<< "$("$AXI_PYTHON" "$SS_ROOT/scripts/configure.py" --benchmark-names "$@")"
mkdir -p "$VORTEX_BUILD"
cd "$VORTEX_BUILD"
"$VORTEX_HOME/configure" --xlen=32 --tooldir="$SS_DEPS_ROOT/xpu-toolchains"
# CMake otherwise clones these sources during the build. Use the same pinned
# source cache for both network and packaged installations.
cmake_sources=(yaml-cpp spdlog argparse)
cmake_args=()
for dependency in "${cmake_sources[@]}"; do
    source_dir="$SS_DEPS_ROOT/cmake-sources/$dependency"
    [[ -f "$source_dir/CMakeLists.txt" ]] || { echo '请先执行 ./run.sh setup' >&2; exit 1; }
    cmake_args+=("-DFETCHCONTENT_SOURCE_DIR_${dependency^^}=$source_dir")
done
cmake -S "$VORTEX_HOME/third_party/ramulator" -B "$VORTEX_HOME/third_party/ramulator/build" "${cmake_args[@]}"
cmake --build "$VORTEX_HOME/third_party/ramulator/build" --parallel "$BUILD_JOBS"
# SoftFloat hardcodes gcc in COMPILE_C; CC alone would be ignored.
softfloat_compile="$AXI_CC -c -Werror-implicit-function-declaration -DSOFTFLOAT_FAST_INT64 "'$(SOFTFLOAT_OPTS) $(C_INCLUDES) -O2 -o $@'
make -C "$VORTEX_HOME/third_party" CC="$AXI_CC" CXX="$AXI_CXX" COMPILE_C="$softfloat_compile" -j "$BUILD_JOBS"
# SimX's upstream makefile also includes Ramulator headers directly. Put the
# pinned include paths first, including when an old ext/ checkout still exists.
vortex_flags="-I$SS_DEPS_ROOT/cmake-sources/spdlog/include -I$SS_DEPS_ROOT/cmake-sources/yaml-cpp/include ${CXXFLAGS:-}"
env -u DEBUG CONFIGS="$simx_flags" CXXFLAGS="$vortex_flags" make -C sim/simx USE_GEM5=1 libvortex-gem5 -j "$BUILD_JOBS"
make -C sw/runtime/stub -j "$BUILD_JOBS"
make -C sw/runtime/gem5 HOST_ARCH=x86_64 -j "$BUILD_JOBS"
# Host optimization flags cannot be passed to the RISC-V compiler.
for benchmark in "${benchmarks[@]}"; do
    # Upstream kernel rules do not track included headers such as softmax/exp.h.
    env -u CFLAGS -u CXXFLAGS -u CPPFLAGS -u LDFLAGS CONFIGS="$simx_flags" make -C "tests/regression/$benchmark" clean
    env -u CFLAGS -u CXXFLAGS -u CPPFLAGS -u LDFLAGS CONFIGS="$simx_flags" make -C "tests/regression/$benchmark" -j "$BUILD_JOBS"
done
cd "$SS_ROOT"
"$AXI_PYTHON" "$SS_ROOT/scripts/configure.py" --record-build "$@"
