# 2. 如何修改参数、选择 benchmark 和查看结果

核对日期：2026-09-25。以下命令均在工程根目录执行。

日常只需修改 [config/run.toml](../config/run.toml)，然后先查看参数，再运行：

```bash
./run.sh config
./run.sh run
```

`config` 不启动仿真。`run` 会执行算例，并继续检查计算结果、AXI、Flit 和在线内存链路。

## 一、先知道 benchmark 在测什么

benchmark 就是用来验证和测量系统的计算程序。目前统一入口支持以下名字：

| 名字 | 做什么 | `elements` 表示什么 | GPU 上的主要计算 |
|---|---|---|---|
| `vecadd` | 两个向量逐项相加 | 向量的元素个数 | `C[i] = A[i] + B[i]` |
| `sgemm` | 单精度浮点矩阵乘法 | 方阵的一条边长 | `C[row,col] = Σ A[row,k] × B[k,col]` |
| `sgemv` | 矩阵乘向量 | 方阵边长，也是输入/输出向量长度；须为 4 的倍数 | `y[row] = Σ A[row,k] × x[k]` |
| `softmax` | 每行转成和为 1 的非负值 | 输入方阵边长 | 每行减最大值、求指数、归一化 |
| `relu` | 负数置零，非负数保留 | 向量元素个数 | `y[i] = max(x[i], 0)` |

例如，`sgemm` 的 `elements = 4` 表示两个 4×4 矩阵相乘，每个矩阵有 16 个元素。
它不是运行 4 层模型，也不是生成 4 个文本 token。

## 二、最常见的三种修改

下面的 TOML 片段用于替换原文件中对应的小节。其余小节保留；当前配置要求字段完整，不会自动补齐缺失参数。

### 1. 把向量规模改成 64

在 `config/run.toml` 中修改：

```toml
[benchmark]
name = "vecadd"
elements = 64
```

然后执行：

```bash
./run.sh config
./run.sh run
```

也可以临时选择已有预设，不修改默认文件：

```bash
./run.sh run --benchmark config/benchmarks/vecadd64.json
```

### 2. 改成矩阵乘法

```toml
[benchmark]
name = "sgemm"
elements = 4
```

或者直接运行已提供的 4×4 预设：

```bash
./run.sh config --benchmark config/benchmarks/sgemm.json
./run.sh run --benchmark config/benchmarks/sgemm.json
```

其他基础算子已有独立预设：

```bash
./run.sh run --benchmark config/benchmarks/sgemv.json
./run.sh run --benchmark config/benchmarks/softmax.json
./run.sh run --benchmark config/benchmarks/relu.json
```

它们分别使用 8×8 矩阵乘 8 元素向量、8×8 逐行 Softmax 和 16 元素 ReLU。计算步骤和数值验算见 [第三篇](03-llm-workload-status.md)。

增大方阵边长会明显增加计算量和输出日志。SGEMM 主机程序还会检查矩阵边长是否能被所选线程块尺寸整除；配置解析接受某个数字，不等于该数字在每种 GPU 配置下都能运行。

### 3. 改 GPU 的并行规模

默认配置为：

```toml
[gpu]
clock_mhz = 1000
cores = 1
warps = 4
threads = 4
```

它表示单簇 1 个核，每核 4 个 warp，每个 warp 4 个线程，设备时钟为 1000 MHz。
这些是硬件模型的配置，并不表示每一拍都能让所有线程完成一条指令。

核数、warp 数和线程数要求是 2 的幂，当前配置解析范围为 1～32。
修改这三项后，`run` 会自动重建 SimX 和 GPU 内核；单改 `clock_mhz` 在下一次运行生效。
配置允许的范围不等于所有组合都已验收，改后应重新检查计算和链路。

## 三、内存参数怎么理解

| 参数 | 通俗含义 | 需要知道的区别 |
|---|---|---|
| `memory.standard` | 选择内存行为模型，如 `hbm4` | 当前完整验收覆盖 HBM4；其他预设仍需单独验证 |
| `memory.channels` | 内存通道数 | 容量要覆盖当前 4 GiB GPU 地址窗口 |
| `memory.scale` | 内存时钟周期倍率 | 值越大，内存时钟越慢；不是把所有仿真时间一起乘大 |
| `memory.queue` | 内存入口、控制器和响应队列深度 | 是排队容量，不是 GPU 线程数 |
| `memory.slots` | 内存桥同时接纳的 AXI burst 数 | 与上面的队列深度作用在不同位置 |
| `memory.response_hold` | 响应额外等待的内存 tick 数 | 通常为 0，可用于反压实验 |

最容易复现的时序对照是：

```bash
./run.sh config --scale 1
./run.sh run --scale 1
./run.sh config --scale 4
./run.sh run --scale 4
```

`--scale 4` 表示本次内存周期倍率设为 4，覆盖文件中的值；它不会在原值上再乘 4。
慢内存会改变请求返回时间，因此可能改变 GPU 的等待周期和总执行周期。

## 四、其他参数通常什么时候改

| 小节 | 用途 | 日常建议 |
|---|---|---|
| `[axi]` | AXI 时钟、在途 TLM 请求、资源平面、反压和 CRC 重放 | 普通计算实验先保持默认 |
| `[host]` | gem5 中运行官方程序的 x86 CPU 上下文、时钟和缓存 | 至少保留 2 个 CPU 上下文，运行库有后台线程 |
| `[simulation]` | 最长允许仿真的时间 | `max_ticks` 单位为 fs，到上限判失败 |

`axi.outstanding` 是 TLM→AXI 桥的在途请求上限，**不是 GPU 指令发射宽度**。
AXI 数据宽度固定为 256 bit，不能仅改 TOML 改成另一种接口宽度。

要测试 CRC 错误恢复，可执行：

```bash
./run.sh config --replay
./run.sh run --replay
```

这里的 replay 指链路出错后的 Flit 重传；内存仍在线响应，不是把预先生成的访存 trace 离线回放。

## 五、怎样保留多份实验配置

复制完整配置，再改副本：

```bash
cp config/run.toml config/my-experiment.toml
# 编辑 config/my-experiment.toml
./run.sh config --config config/my-experiment.toml
./run.sh run --config config/my-experiment.toml
```

配置优先级是：**所选 TOML → 本次命令行覆盖**。
`--benchmark` 替换算例，`--scale` 替换内存倍率，`--replay` 开启错误注入和重放；均不写回 TOML。

配置路径相对于工程根目录；`--output` 相对于调用命令时的目录。
不传 `--output` 时，每次自动创建新的结果目录。手动指定时也必须用尚不存在的目录：

```bash
./run.sh run --output results/my-experiment-001
```

## 六、什么时候需要重新编译

| 改了什么 | 怎么做 |
|---|---|
| 算例规模、GPU 时钟、内存/AXI 运行参数 | 直接 `./run.sh run` |
| GPU 核数、warp/线程数 | `run` 自动重建设备及全部已接入算例 |
| 同一 GPU 配置下切换已接入的 benchmark | 已构建时直接运行，无需重建设备库 |
| `config/simx.toml` 高级默认值 | `run` 检测完整配置文本变化，自动重新 configure 和构建 |
| C++ 源码、GPU kernel、gem5 适配、接口实现 | 先 `./run.sh build`，再运行和验收 |
| 使用另一份完整配置进行源码重建 | `./run.sh build --config config/my-experiment.toml` |

高级缓存、ISA、调度参数在 [config/simx.toml](../config/simx.toml)。构建时同步到本工程 Vortex 的 `VX_config.toml`；日常核数/warp/线程数由 `run.toml` 覆盖。

固定地址定义在 [config/addrmap.json](../config/addrmap.json)，它必须与驱动和内核的地址约定一致。修改地址需要同步修改相应源码，不能把它当成普通调参项。

## 七、源码和运行产物在哪里

| 想找什么 | 位置 |
|---|---|
| vecadd 的输入生成、提交和 CPU 验算 | [vecadd/main.cpp](../third_party/vortex/tests/regression/vecadd/main.cpp) |
| vecadd 的 GPU 计算 | [vecadd/kernel.cpp](../third_party/vortex/tests/regression/vecadd/kernel.cpp) |
| SGEMM 的输入生成、提交和 CPU 参考结果 | [sgemm/main.cpp](../third_party/vortex/tests/regression/sgemm/main.cpp) |
| SGEMM 的 GPU 计算 | [sgemm/kernel.cpp](../third_party/vortex/tests/regression/sgemm/kernel.cpp) |
| LLM 基础算子的主机程序和 GPU 内核 | [sgemv](../third_party/vortex/tests/regression/sgemv/)、[softmax](../third_party/vortex/tests/regression/softmax/)、[relu](../third_party/vortex/tests/regression/relu/) 各自的 `main.cpp`、`kernel.cpp` |
| 官方 gem5 运行库 | [sw/runtime/gem5/](../third_party/vortex/sw/runtime/gem5/) |
| 构建程序、传递编译参数 | [scripts/build_device.sh](../scripts/build_device.sh) |
| 组装命令并启动 gem5 | [scripts/run.py](../scripts/run.py)、[scripts/simulate.py](../scripts/simulate.py) |
| 生成的主机程序和 GPU 镜像 | `build/vortex/tests/regression/<名称>/` 下的同名主机程序、`kernel.vxbin` |

修改计算功能，应改源码目录中的 `kernel.cpp`，并检查 `main.cpp` 中的参考结果是否仍适用；不要直接修改 `build/` 里的生成文件。

`./run.sh build` 会先清理再重编全部已接入算例，避免上游 Makefile 漏掉头文件变化。因此修改 `common.h`、Softmax 的 `exp.h` 等文件后，也使用同一个构建命令。

如果要新增表中之外的 benchmark，仅在配置中填新名字还不够。需要加入本项目内的主机/kernel 源码、构建规则，扩展 `configure.py` 的 `BENCHMARKS`、参数校验与启动参数，并为计算结果和完整链路增加验收。现有算例的成功不能代替新算例的验收。

## 八、怎样判断这次运行真的成功

```bash
./run.sh check   # 环境、动态库和设备隔离检查
./run.sh test    # 原生内存、C ABI 和完整计算/链路验收
```

`check` 通过只说明环境可用。完整 `test` 先检查 Softmax 指数近似误差、原生内存与 C ABI，再运行默认、慢内存、CRC 重放、64 元素向量、SGEMM、SGEMV、Softmax、ReLU 共 8 个端到端场景。
慢内存对照会把所选配置的内存周期再放慢 4 倍，因此用于 `test` 的 `memory.scale` 须不大于 256。

结果目录里优先看以下内容：

| 文件 | 回答什么问题 |
|---|---|
| `resolved.json` | 本次到底用了什么参数、地址和 SimX 高级默认值 |
| `run.log` | 官方程序是否验算通过，实际加载的 GPU 配置和执行周期是什么 |
| `summary.json` | 计算、协议、内存、波形等检查是否全部通过 |
| `completion.json` | 仿真是否正常结束；这一项单独不能证明完整验收通过 |
| `axi_wave.vcd`、Flit/内存日志 | 每一层是否真实发生了请求和返回 |
| `memsim_view.html` | 按请求查看在线内存和链路结果 |

本机最近一次完整验收见 [验收说明](../validation/2026-09-25-llm/README.md)：19 项原生测试和 8 个端到端场景全部通过。源码或配置发生变化后，应生成新的结果目录重新核对。
