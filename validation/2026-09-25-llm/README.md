# LLM 基础算子接入后的实际验收

验收日期：2026-09-25。使用本项目源码、构建产物和官方运行库，运行链路为 Vortex SimX → gem5 timing → AXI256 → AXI2Flit → UCIe → 在线 mem_sim。

配置副本为 [run.toml](run.toml)：GPU 为 RV32、单簇 1 核、每核 4 个 warp、每 warp 4 线程、1000 MHz；内存为 HBM4、8 通道，统一 1 fs 时间基准。每个场景的实际配置与文件名/大小记录分别在 `resolved.json`、`environment.json`。

执行命令：

```bash
./run.sh build
./run.sh test --output results/acceptance-llm-fp32-20260925
```

[总汇总](summary.json) 为 `passed: true`；没有复用旧用例。mem_sim 原生测试 19/19、在线 C ABI、指数误差扫描和 8 个端到端场景全部通过。

| 用例 | GPU 周期 | 核心 + CP 完成请求数 | 数值、AXI、Flit、内存、波形 |
|---|---:|---:|---|
| [default](default/summary.json) | 626 | 95 | PASS |
| [slow](slow/summary.json) | 1032 | 95 | PASS |
| [replay](replay/summary.json) | 614 | 95 | PASS |
| [alternate](alternate/summary.json) | 1615 | 107 | PASS |
| [sgemm](sgemm/summary.json) | 1450 | 98 | PASS |
| [sgemv](sgemv/summary.json) | 1716 | 132 | PASS |
| [softmax](softmax/summary.json) | 7418 | 110 | PASS |
| [relu](relu/summary.json) | 885 | 91 | PASS |

默认与慢内存的完成请求数均为 95，内存周期放慢 4 倍后，GPU 周期由 626 增至 1032。原有五个场景的 GPU 周期与上一轮配置整理验收一致。

## 数值检查

- SGEMV：8×8 矩阵乘 8 元素向量，8 个结果全部通过，最大绝对误差 `5.96046448e-08`。
- Softmax：8×8 逐行归一化，64 个结果全部通过，最大绝对误差 `1.78178876e-08`，最大行和误差 `3.44589353e-08`。参考值由主机双精度 `std::exp` 独立计算。
- ReLU：16 个结果与参考值完全相等，覆盖 6 个负数、2 个零和 8 个正数。
- [指数扫描](softmax-exp-check.json)：主机扫描 1,000,001 个输入点，误差条件全部满足；`[-80, 0]` 内的最大相对误差为 `9.83601222398e-08`。GPU 的数值正确性另外由实际算例验算。

三个算子的实际 `LLM_CHECK`、`PASSED!` 和时序统计保存在各自 `run.log` 中，检查器读入数值报告后继续核对完整链路。实现与误差标准见 [LLM 算子说明](../../docs/03-llm-workload-status.md)。

## 接入时发现并处理的问题

首次尝试调用工具链 `expf` 时，Softmax 数值检查失败，最大绝对误差约 0.529；该库路径会使用软件双精度函数，其内部故障点尚未确定。当前算子采用内核内的 FP32 范围缩减和七次多项式，保留原输出误差标准；没有把库问题认定为已修复。

ReLU 的两笔 24 字节 CP 请求各拆成两个 burst，暴露了检查器将请求数与 burst 数直接比较的问题。现按 `transactions.csv` 的实际 `segments` 总数与观察记录比较，继续要求读写字节数、五通道握手、Flit、内存数据和波形全部通过。

统一构建还改为先清理再重编算例，避免上游规则漏掉头文件变化。修改构建步骤后再次执行 `./run.sh build`，5 个算例的主机程序和 GPU 镜像共 10 个文件与本轮通过验收的产物逐字节一致，见 [重建核对](clean-rebuild-check.json)。

首次失败的[摘要](initial-failure.json)及完整原始目录 `results/acceptance-llm-20260925/` 保留；该轮总结果为失败，不作为本轮通过依据。

## 证据与范围

本目录保存配置、数值报告、主机运行日志和协议/内存/波形摘要。完整 AXI 五通道 VCD、两端 Flit、内存请求/返回、DRAM/DFI、最终内存镜像及 HTML 保留在 `results/acceptance-llm-fp32-20260925/`。

这是已运行规模下的独立基础算子验收，没有加载完整语言模型或实现逐 token 生成。SimX 是 C++ 功能/周期模型，内存 PHY/DFI 是行为模型，HBM4 预设含临时时序项；结果不代表完整 GPU RTL 或真实芯片的绝对性能。
