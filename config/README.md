# 配置说明

日常只编辑 [`run.toml`](run.toml)。原来的 `architecture.json`、`benchmark.json`
已经合并到这个文件，每个字段旁都有中文注释。

```bash
./run.sh config                         # 检查并查看最终参数，不启动仿真
./run.sh config --json                  # 查看完整 JSON（含地址/时间基准）
./run.sh run                            # 按 run.toml 执行并验收
./run.sh config --scale 4                # 预览慢内存实验
./run.sh run --scale 4                   # 实际运行同一配置
./run.sh run --benchmark config/benchmarks/sgemm.json
./run.sh test                           # 完整计算与链路验收
```

新实验可复制 `run.toml` 为 `config/my-experiment.toml`，然后执行
`./run.sh run --config config/my-experiment.toml`。
`config`、`build`、`run`、`test` 都支持 `--config`。
test 将所选配置的内存周期再放慢 4 倍进行对照，因此验收配置的 `memory.scale` 须不大于 256。
相对配置路径以工程根目录为准；`--output` 以调用命令时的目录为准。

配置优先级只有两层：完整 TOML，然后是本次命令行覆盖。
`--benchmark` 替换 `[benchmark]`，`--scale` 替换 `memory.scale`，
`--replay` 开启 `axi.replay`；不写回配置。
字段拼错、缺失、类型/范围不合法时直接报错，不隐式补全。
`results/.../resolved.json` 是当次使用的完整快照，验收继续核对 gem5 实际实例化的参数。

| 常改项 | 含义 | 生效方式 |
|---|---|---|
| `benchmark.name` | `vecadd`、`sgemm`、`sgemv`、`softmax`、`relu` | 首次/架构改变时构建全部算例；同配置切换直接运行 |
| `benchmark.elements` | vecadd/relu 向量长度；其余为方阵边长，sgemv 要求 4 的倍数 | 下一次运行 |
| `gpu.clock_mhz` | SimX 设备频率；周期必须是整数 fs | 下一次运行 |
| `gpu.cores/warps/threads` | 单簇核数、每核 warp 数、每 warp 线程数；2 的幂 | run 自动重建 SimX 与内核 |
| `memory.standard` | `hbm3/hbm4/lpddr5/lpddr6` 行为模型预设 | 下一次运行；已验收范围见 ACCEPTANCE.md |
| `memory.channels` | 内存通道数；容量必须覆盖 4 GiB GPU 窗口 | 下一次运行 |
| `memory.scale` | 内存时钟周期倍率，越大越慢 | 下一次运行；会反馈到 GPU 周期 |

`[axi]`、`[host]`、`[simulation]` 和其他队列参数用于高级实验，通常保持默认。
`axi.outstanding` 是 TLM→AXI 桥的在途请求上限，`memory.slots` 是内存桥的在途 burst 上限，
`memory.queue` 是内存队列深度；它们作用于不同阶段，不应当作同一个“GPU 发射数”。
`axi.stalls` 和 `axi.replay` 用于反压/错误注入验证，`memory.response_hold` 为额外响应延迟。
`simulation.max_ticks` 是 watchdog 上限，1 tick = 1 fs；到限判失败。

官方运行库有后台线程，`host.num_cpus` 至少为 2。
主机执行程序/栈放在本地主存，GPU BAR 数据放在在线 mem_sim；这两条地址范围不重叠。
AXI 数据宽度固定 256 bit，WSTRB 固定 32 bit，不能通过改 TOML 改接口 ABI。

## 高级文件

| 文件 | 职责 |
|---|---|
| `simx.toml` | 上游 GPU 缓存、ISA、调度等完整默认值；普通实验不用改 |
| `addrmap.json` | 固定 CP/主机/BAR 地址 ABI、来源定义与 1 fs 时间基准 |
| `benchmarks/*.json` | 可选 benchmark 预设，只含名称和规模 |
| `environment.sh` | 本机工具目录与编译并行度 |
| `sources.json` / `conda-linux-64.lock` / `xpu-artifacts.lock.json` | 源码与工具版本、文件名和大小记录 |
| `$STORAGE_STACK_ROOT/config/memory/` | mem_sim 原生独立实验的配置，不覆盖主链路 TOML 的 `memory` 参数 |

构建会将 `simx.toml` 同步到本项目 Vortex 的 `VX_config.toml`，
`run.toml` 的核数/warp/线程数通过编译参数覆盖高级默认值。
run 比较完整高级配置文本与构建记录，变动时自动重新 configure 并构建设备和内核。
SGEMV、Softmax、ReLU 的实现、数值检查和运行方式见 [LLM 算子说明](../docs/03-llm-workload-status.md)。
修改 C++ / RTL / 接口源码后仍需 `./run.sh build`，然后在新目录重新验收。
显式构建会先清理再重编全部已接入算例，保证算例头文件的修改也生效。
地址是官方驱动 ABI，不支持仅改 JSON；启动时检查，避免主机、设备与内存使用不同地址。

当前验收为 RV32、单 cluster、SimX C++ 功能/周期模型。
上游 TOML 的 RTL 专用参数不保证影响 SimX，也不代表所有微架构组合均已验收。
PHY/DFI 是行为模型，HBM4 预设含临时时序项；周期准确性限定于当前模型与配置。

## 独立存储依赖

`storage_dependency.json` 声明公共项目版本和 AXI 接口。默认使用同级 `axi_StorageStacked`，
可通过 `STORAGE_STACK_ROOT` 指定其他位置。存储原生配置仅存在于公共项目；
本驱动的架构/运行配置仍决定本次在线链路参数。修改公共 C++ 源码后对使用它的驱动执行 build。
