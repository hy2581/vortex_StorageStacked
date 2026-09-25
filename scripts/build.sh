#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/activate.sh"
"$AXI_PYTHON" "$SS_ROOT/scripts/configure.py" "$@"
mkdir -p "$SS_ROOT/build"
exec 9>"$SS_ROOT/build/build.lock"
flock 9
"$AXI_PYTHON" "$SS_ROOT/scripts/gen_addrmap.py"
"$AXI_PYTHON" "$AXI_PROJECT_DIR/scripts/patch_gem5.py" "$GEM5_HOME"
patch_file="$HET_PROJECT_ROOT/patches/dma_byte_enable.patch"
if ! patch -R -p1 -s -f --dry-run -d "$GEM5_HOME" -i "$patch_file" >/dev/null 2>&1; then
    patch -p1 -s -f -d "$GEM5_HOME" -i "$patch_file"
fi
mkdir -p "$GEM5_HOME/src/dev/vortex" "$GEM5_HOME/src/hettrace"
cp "$HET_PROJECT_ROOT/dev/vortex/"* "$GEM5_HOME/src/dev/vortex/"
cp "$HET_PROJECT_ROOT/include/hettrace/"*.h "$GEM5_HOME/src/hettrace/"
cmake -S "$MEMSIM_HOME" -B "$MEMSIM_BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_CXX_COMPILER=$AXI_CXX"
cmake --build "$MEMSIM_BUILD" -j "$BUILD_JOBS"
cd "$GEM5_HOME"
build_args=("CXX=$AXI_CXX" "CC=$AXI_CC" "PYTHON_CONFIG=$PYTHON_CONFIG" "EXTRAS=$AXI_PROJECT_DIR:$HET_PROJECT_ROOT/hettrace:$STORAGE_STACK_ROOT/storage_axi")
if [[ ! -f build/AXI/gem5.build/config ]]; then
    "$GEM5_SCONS" defconfig build/AXI build_opts/X86 "${build_args[@]}"
fi
"$GEM5_SCONS" setconfig build/AXI RUBY=n USE_KVM=y USE_SYSTEMC=y "${build_args[@]}"
"$GEM5_SCONS" build/AXI/gem5.opt "${build_args[@]}" -j "$BUILD_JOBS"
bash "$SS_ROOT/scripts/build_device.sh" "$@"

"$AXI_PYTHON" "$SS_ROOT/scripts/storage_dependency.py" --record-build
