# SimX 与 gem5 如何连接

唯一生产链路由 [`scripts/simulate.py`](../scripts/simulate.py) 建立。
它按三部分组织：`connect_host` 放置官方主机程序，`connect_gpu` 挂接 SimX，
`connect_memory` 连接完整外部内存链路；所有地址取自当次配置快照。

```text
官方 host 程序 / gem5 runtime
  ├─ 程序、栈、堆 → gem5 本地主存
  ├─ CP MMIO → Vortex 命令处理器 → 启动 SimX 内核
  └─ GPU BAR 上传/下载 ─────────────────────┐
                                          ↓
SimX 指令/warp/缓存 → 外部访存 → gem5 DMA → 系统总线
CP 队列/数据搬运 ─────────────→ gem5 DMA ──┘
                                          ↓
                               观察器 → 原生 TLM → AXI256
                                          ↓
                               AXI2Flit → UCIe → mem_sim
                                          ↓
                              数据/完成沿原路径返回请求方
```

## 一次 GPU 外部访存

1. gem5 的 `vortexTick()` 调用设备库 `vortex_gem5_vortex_tick()`，后者推进
   原生 SimX `Processor::cycle()`。GPU 指令仍由 SimX 解码执行。
2. SimX `Memory` 模块从缓存后的通道取请求，生成 token，经 external timing hook
   交给 gem5 设备 `issueCoreTiming()`。缓存命中无需走外部内存。
3. 设备记录请求和数据缓冲，调用 gem5 `dmaRead` / `dmaWrite`；写请求携带字节使能。
   gem5 负责 timing 请求、重试与返回事件，下游执行真实 AXI/Flit/内存传输。
4. `coreDmaComplete(token)` 收到完成事件后，将读数据或写完成通知交给
   `complete_core_memory()`；SimX `Memory` 再向自身响应通道交付数据。

CP 也使用同一个 gem5 DMA 端口。CP 的同步读写接口由协程挂起，等 timing 响应后恢复；
没有提前读一份本地副本再补记延迟。主机对 GPU BAR 的读写则直接由系统总线进入在线链路。

| 代码入口 | 职责 |
|---|---|
| `dev/vortex/vortex_gpgpu_dev.cc` | gem5 事件调度、核心/CP DMA 请求与完成 |
| `vortexint/patches/simx_online.patch` | 对本项目上游 SimX 添加外部请求与完成接口 |
| `../third_party/vortex/sim/simx/gem5/vortex_gpgpu.cpp` | SimX 动态库 C ABI、`Processor::cycle()` |
| `../third_party/vortex/sim/simx/mem/memory.cpp` | 缓存后的请求通道、token 与返回通道 |
| `hettrace/het_axi_monitor.cc` | 观察实际 gem5 packet，生成来源记录 |
| `../scripts/verify.py` | 对照实际运行配置、计算、返回与各层证据进行验收 |

## 时间、队列和计数

所有模块共享 gem5 的 1 fs 时间基准，只用 gem5 自带的 SystemC。
GPU、AXI 和内存可有不同周期；`memory.scale=4` 改的是内存周期，不会将整个仿真时间统一乘四。
慢内存通过响应到达时间影响 GPU，完整验收要求观察到这一反馈。

SimX 请求可能被 gem5/AXI 拆分，一次 AXI burst 又会变成多个 beat、Flit 和内存子请求。
因此核心/CP 请求总数、来源 trace 事务数、AXI beat 数不能直接相等比较。
HETTrace 是 gem5 packet 的协议投影；真实五通道握手检查使用 AXI VCD 和通道日志。

`axi.outstanding`、`memory.slots`、`memory.queue` 各自限制桥、burst 和内存队列；
GPU 指令发射与 warp 调度仍由 SimX 微架构决定。本次整理保持这些执行规则。
该模型用于功能及模型内时序比较；完整 GPU RTL、真实芯片绝对性能、通用 atomic/functional
访问和跨设备缓存一致性不在已验收范围内。
