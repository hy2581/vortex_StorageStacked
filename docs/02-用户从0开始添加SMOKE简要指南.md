# 用户从 0 开始添加 SMOKE 简要指南

先在仓库根目录执行一次 `./build.sh`。下面所有命令在 `user/` 中执行。

## 1. 新建项目目录

```bash
mkdir -p my_smoke/src
```

## 2. 保存项目配置

复制完整平台配置，然后修改输入值和工作组数：

```bash
cp smoke/config.json my_smoke/config.json
python3 - <<'PY'
import json
from pathlib import Path
p=Path('my_smoke/config.json')
c=json.loads(p.read_text())
c['program']={'type':'smoke','input':41,'workers':4}
p.write_text(json.dumps(c,indent=2)+'\n')
PY
```

需要修改 GPU、CPU/MMU/缓存、AXI、UCIe 或 MEMSIM 时，直接改这一个 JSON。完整字段见[环境配置说明](01-用户环境配置说明.md)。写 JSON 是在磁盘上保存配置文件；设备程序运行后才会向模拟内存写数据。

## 3. 准备 CPU 和 GPU 两份源码

复制可直接阅读的 CPU 程序。它创建多个线程准备输入，通过 Vortex API 上传和发射，回读后再分片检查：

```bash
cp smoke/src/host.cpp my_smoke/src/host.cpp
```

编写 GPU 程序，只负责读取 CPU 已上传的输入、加一和写回：

```bash
cat > my_smoke/src/kernel.cpp <<'CPP'
#include "project_config.h"
#include <vx_spawn2.h>
#include <cstdint>

__kernel void kernel_main() {
    const unsigned index = blockIdx.x;
    volatile uint32_t *input = (volatile uint32_t *)0x90000000u;
    volatile uint32_t *output = (volatile uint32_t *)0x90010000u;
    volatile uint32_t *status = (volatile uint32_t *)0x9005000cu;
    const uint32_t value = input[index];
    output[index] = value + 1u;
    const uint32_t returned = output[index];
    if (index == 0)
        *status = returned == value + 1u ? 0x600d0000u : 0xbad00001u;
}
CPP
```

每个 GPU 工作组读取输入、加一、写入输出、再读回。`project_config.h` 由 SDK 根据本次 JSON 生成，无需手写。地址是 GPU 程序使用的地址，外部请求经 gem5 映射进入公共存储窗口。

## 4. 编写 Makefile

```bash
cat > my_smoke/src/Makefile <<'MAKE'
HOST_SOURCES := host.cpp
KERNEL_SOURCES := kernel.cpp
SDK := ../../../third_party/sdk
include $(SDK)/app.mk
MAKE
```

Makefile 明确声明两类源码：`host.cpp` 生成 x86-64 的 `host.elf`，在 gem5 CPU 执行；`kernel.cpp` 生成 RV32 的 `program.elf` 和 `program.vxbin`，在 Vortex GPU 执行。

## 5. 运行

```bash
./run.sh my_smoke --output result/first
```

无需修改 `run.sh` 或登记项目名。入口自动读取 `my_smoke/config.json` 和 `my_smoke/src/Makefile`。

## 6. 看输出

```bash
cat my_smoke/result/first/report.md
cat my_smoke/result/first/smoke_summary.json
cat my_smoke/result/first/host_summary.json
```

预期为输入 `41`、输出 `42`、`workers: 4`、`passed: true`，四个工作组的输出均被独立检查。默认四个 CPU 核应均有提交指令、L1 访问和 MMU 样本；报告直接列出各核数据。

```mermaid
flowchart LR
    A[config.json] --> B[Makefile 编译]
    C[host.cpp + kernel.cpp] --> B
    B --> D[gem5 CPU 准备和发射 / Vortex GPU 计算]
    D <--> E[AXI / UCIe / MEMSIM]
    D --> F[回读输出并独立校验]
    E --> F
    F --> G[result/first/report.md]
```

## 7. 添加自己的计算

保留同样目录结构，修改 `src/` 和 Makefile；把 `program.type` 改为 `custom`，用 `defines` 提供整数宏、`expect` 提供输出地址与期望值。例如：

```json
"program": {
  "type": "custom",
  "workers": 1,
  "defines": {"INPUT": 41},
  "expect": [{"address": "0x90010000", "value": 42}]
}
```

自定义项目也必须提供 `host.cpp` 和 `kernel.cpp`。根据自己的输入输出修改 CPU 的准备、上传和检查代码，不能原样复用只检查 SMOKE 的主机逻辑。设备可通过 `APP_INPUT` 读取该输入，把结果写入期望地址，最后向 `0x9005000c` 写 `0x600d0000`。用户数据区为 `0x90000000`～`0x9005ffff`；输出字地址须 4 字节对齐。成功状态之后还会逐字检查真实返回数据和完整链路。

## 8. 改 CPU 核数

把 `my_smoke/config.json` 的 `host.num_cpus` 改为 `2`，再运行：

```bash
./run.sh my_smoke --output result/cpu2
```

与四核结果比较 `host_summary.json` 的 `active_cpus`、每核指令数和线程分片。输出仍为 42；这里观察实际任务分配，短示例不要求核数增加就加速。
