# vortex_StorageStacked

Vortex SimX 在 gem5 的事件队列中执行 GPU 内核；gem5 中的 x86 主机只负责官方运行库与 benchmark 的控制、输入和结果检查。

```text
gem5 主机 + Vortex SimX
  → gem5 timing 请求 → 原生 TLM → AXI256 五通道
  → AXI2Flit → 双向 UCIe → mem_sim 控制器 / 行为级 PHY
  ← 沿原路径返回真实读数据和写完成
```

## 从 GitHub 获取

```bash
git clone https://github.com/hy2581/axi_StorageStacked.git
git clone https://github.com/hy2581/vortex_StorageStacked.git
cd vortex_StorageStacked
./run.sh setup
./run.sh build
./run.sh run
```

驱动源码直接保存在本仓库，包含 `third_party/` 中的 gem5 与 Vortex。AXI 信号之后的完整存储链路位于独立的 `axi_StorageStacked` 仓库；不使用 submodule。
`setup` 只检查源码快照并准备工具依赖，不递归拉取 Git 仓库。
Git 保存源码、配置、补丁、许可证和 `validation/` 验收摘要；本机工具链、编译缓存和完整波形由构建/运行生成。
Vortex 的可选工艺库、无关系统包和大型 OpenCL 数据集不属于本项目 SimX 构建输入，留在本机。

## 在本机运行

首次了解本工程，可按顺序阅读以下三篇中文说明：

1. [对 Vortex 做了哪些修改](docs/01-vortex-changes.md)
2. [如何修改参数和配置 benchmark](docs/02-configuration-and-benchmarks.md)
3. [当前 LLM 负载状态与计算位置](docs/03-llm-workload-status.md)

```bash
cd /home/hy258/hy/zhongxing/vortex_StorageStacked
./run.sh check
./run.sh run
```

`check` 检查环境、动态库、设备隔离；`run` 才会执行 benchmark 并校验数据与完整链路。
结果默认写入新的 `results/时间戳/`，禁止覆盖已有目录。
成功以 `summary.json` 的 `passed: true` 为准，失败保留日志和 `passed: false`。

## 配置和重新构建

**日常只改 [`config/run.toml`](config/run.toml)**，每项都有中文注释。
文件开头选择 benchmark 和 GPU 核数/warp/线程数，后面设置内存、链路和主机。
所有配置均在 [`config/`](config/README.md)；缓存/ISA 等高级 SimX 默认值在 `config/simx.toml`。

```toml
# config/run.toml 开头；其余参数通常保持默认。
[benchmark]
name = "vecadd"
elements = 64

[gpu]
clock_mhz = 1000
cores = 1
warps = 4
threads = 4
```

```bash
# 新环境：只准备本工程需要的固定版本依赖
./run.sh setup
# 首次或修改 C++ / RTL / 适配源码后重新构建
./run.sh build
# 查看最终参数、访存路径和是否需要重新构建设备
./run.sh config
# 运行并校验；GPU 架构改变时自动重建设备和全部已接入算例
./run.sh run --output results/my-case
# 使用另一份完整配置；相对路径从工程根目录解析
./run.sh run --config config/my-experiment.toml
# 选择另一份 benchmark 配置
./run.sh run --benchmark config/benchmarks/vecadd64.json
# 常见 LLM 基础算子：矩阵向量乘、Softmax、ReLU
./run.sh run --benchmark config/benchmarks/sgemv.json
./run.sh run --benchmark config/benchmarks/softmax.json
./run.sh run --benchmark config/benchmarks/relu.json
# 内存延迟与重放实验
./run.sh run --scale 4
./run.sh run --replay
# 完整验收：原生内存、C ABI、链路对照及全部已接入算子
./run.sh test
```

所有路径参数均可使用绝对路径；benchmark 的相对路径相对于本工程根目录，
`--output` 的相对路径相对于调用命令时的工作目录。

GPU 编译参数或 SimX 高级默认值改变时，run 自动构建设备与全部已接入内核。
同一 GPU 配置下切换 vecadd、sgemm、sgemv、softmax、relu 无需重建设备库。
`--benchmark` 只替换算例，`--scale` / `--replay` 只覆盖本次实验；
同样的参数可交给 `./run.sh config` 预览，最终生效值保存在结果目录的 `resolved.json`。

## 如何发射和完成访存

GPU 指令、warp 调度和缓存由原生 SimX 执行；gem5 的事件队列每个设备周期推进一次 SimX。
SimX 缓存之后的外部请求通过适配层调用 gem5 `dmaRead` / `dmaWrite`，
沿上图进入在线 mem_sim；返回事件将真实读数据或写完成交回 SimX。
命令处理器 CP 的 DMA 也走同一条 gem5 timing 链路，并等待响应再继续。
主机程序/栈使用独立的本地主存；主机对 GPU BAR 的上传、下载走完整在线链路。

`axi.outstanding` 是桥中同时处理的 TLM 请求上限，不是 GPU 指令发射宽度。
缓存命中不经过外部链路，SimX 请求、gem5 packet、AXI beat 和 Flit 的计数也不相等。
代码入口与请求/返回职责见 [`integration/README.md`](integration/README.md)。

## 目录

| 目录 | 用途 |
|---|---|
| `config/` | 所有公开配置、benchmark 预设、版本锁定、配置说明 |
| `scripts/` | 一套 setup/build/run/test/check 入口与唯一仿真拓扑 |
| `integration/` | 仅本设备的 gem5 适配、协议观察器和必要外部补丁 |
| `benchmarks/` | 本项目 benchmark 源码或官方源码入口说明 |
| `gem5_axi/` | 原生 TLM → AXI256 驱动适配；存储实现由公共项目提供 |
| `../axi_StorageStacked/` | 独立公共依赖：AXI 信号端口、AXI2Flit、UCIe、在线内存和共用验收器 |
| `third_party/` | 本项目自己的 gem5 和 vortex 固定版本源码 |
| `.deps/` | 本驱动自己的工具链、编译依赖和缓存 |
| `build/`、`results/` | 编译产物和实际运行证据 |

两个驱动互不链接，均通过公共 AXI256 端口驱动同一份 `axi_StorageStacked` 源码。
默认依赖路径为 `../axi_StorageStacked`；不同目录可用 `export STORAGE_STACK_ROOT=/绝对路径/axi_StorageStacked` 指定。
切换公共项目路径或版本后必须重新 build；运行入口会拒绝路径与构建记录不一致的二进制。
依赖声明在 `config/storage_dependency.json`，每次运行在 `environment.json` 记录公共项目版本/提交号。
内存库分别编译到各驱动的 `build/memsim/`，不会共用另一个驱动的二进制。
本次从本机已准备的固定版本源码与包缓存建立环境，分别在新目录重编译。
源码来源见 `config/sources.json`，当前分拆说明见 `SPLIT_NOTES.md`。
复制到不同路径后执行 setup/build，重建含绝对 RPATH 的产物；不要直接搬用旧编译缓存。
新机器需要 Linux x86-64、Bash、Git、curl、make、patch、tar、C/C++ 基础开发工具与网络，
建议至少 32 GB 内存。默认编译并行度为 12，可在 `config/environment.sh` 修改。
`SS_OFFLINE=1` 禁止 setup 下载；离线准备需要预置完整源码和依赖缓存。

## 验收证据与边界

本次实际执行结果见 [`ACCEPTANCE.md`](ACCEPTANCE.md)。

每次运行保存 `resolved.json`、`environment.json`、`completion.json`、`summary.json`，
并保留 AXI 五通道 VCD、两端 Flit、内存请求/返回、DRAM 命令、DFI、最终内存镜像、
来源 trace 和分块 HTML。`memsim_view.html` 可按请求查看链路；
在工程目录执行 `python3 -m http.server 8000` 后通过浏览器打开结果页面，交接时复制整个用例目录。

来源 HETTrace 是 gem5 packet 的协议投影，实际 AXI 握手以 `axi_wave.vcd` 和五通道日志为准。
仅使用 gem5 自带的一套 SystemC，统一时间单位为 1 fs。
SimX 是 C++ 功能/周期模型，不是完整 GPU RTL；主机程序和栈留在本地主存，GPU 缓冲区通过在线链路。
内存 PHY/DFI 为行为模型，HBM4 预设含临时时序项；结果用于本模型的功能与时序比较。
当前不支持完整链路上的通用 functional/atomic 访问、checkpoint 或跨设备缓存一致性。

长验收允许续跑：`./run.sh test --resume --output results/已有验收目录`。
仅复用配置、来源版本和产物大小匹配的已通过场景；更改源码后使用新目录重新验收。
同一编译配置的场景并行运行，重新编译设备时使用独占锁，防止运行中替换动态库。
