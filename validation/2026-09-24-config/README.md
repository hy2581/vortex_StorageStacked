# 配置简化后的实际验收

本次保留官方 host/runtime、原生 SimX 计算和完整在线 gem5 timing 链路。
日常配置合并为 `config/run.toml`；本目录的 `run.toml` 是本次配置副本。

执行命令：

```bash
./run.sh build
./run.sh config
./run.sh test --output results/acceptance-config-20260924
```

总结果：[`summary.json`](summary.json) 中 `passed: true`。
mem_sim 原生测试 19/19、在线 C ABI 检查和五个计算/链路用例全部通过。

| 用例 | GPU 周期 | 核心 + CP 完成请求数 | 计算、AXI、Flit、内存、波形 |
|---|---:|---:|---|
| [default](default/summary.json) | 626 | 95 | PASS |
| [slow](slow/summary.json) | 1032 | 95 | PASS |
| [replay](replay/summary.json) | 614 | 95 | PASS |
| [alternate](alternate/summary.json) | 1615 | 107 | PASS |
| [sgemm](sgemm/summary.json) | 1450 | 98 | PASS |

[`compute-comparison.json`](compute-comparison.json) 记录与配置整理前的实测结果对照，
GPU 周期以及核心/CP 读写、完成请求、CP 周期计数一致。
慢内存时钟周期放大 4 倍，GPU 周期从 626 增至 1032，验证响应时序继续反馈到执行。

配置检查见 [`config-checks.json`](config-checks.json)：默认参数与原验收一致；
自定义 GPU/时钟参数进入配置解析和编译参数；benchmark/scale/replay 覆盖正确；
错误字段、类型、时钟及缓存集合尺寸在启动前被拒绝。
自定义 8 线程/500 MHz 在此只做配置与编译参数解析检查，不作为端到端验收场景。

每个用例额外核对实际加载的 SimX 配置、gem5 timing 模式、主机/GPU 时钟、
CP/BAR/本地主存地址、在线内存参数，以及 HETTrace 的 1 fs 时间单位和源周期。

完整原始证据位于 `results/acceptance-config-20260924/`，包括 AXI 五通道 VCD、
两端 Flit、内存请求/返回、DRAM/DFI、最终内存镜像和 HTML。
本目录只保存摘要与配置，未覆盖原来的 `validation/2026-09-24/`。

范围仍为 RV32、单 cluster、SimX C++ 功能/周期模型与 HBM4 行为内存；
HBM4 预设含临时时序项，不代表真实芯片或完整 GPU RTL 的时序精度。
