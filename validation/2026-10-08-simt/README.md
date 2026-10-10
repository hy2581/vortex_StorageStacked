# SIMT 与单次回归验收

从仓库根目录执行一次：

```bash
./build.sh --test
```

平台回归将默认 SMOKE 与默认 LLM 各运行一次，并完成原生内存、在线接口、
独立数值、CPU 实际执行、AXI／Flit／内存／波形与错误拒绝检查。
单独验收 LLM 时，在 `user/` 中执行 `./run.sh llm --test`，默认 LLM 仿真运行一次。

TinyLLM 使用一个工作组，线程数为 `min(8, gpu.threads × gpu.warps)`。
默认配置发射 8 个线程、2 个 warp，在一个 GPU 核上执行。
线性层按输出列分工，每列按输入行顺序完成 FP32 乘法与加法。
LayerNorm、注意力、Softmax、贪心选择与观测记录由组内线程 0 处理。
中间数组放在共享局部内存，阶段之间使用工作组屏障，串行阶段与输出列尾块使用显式 `vx_split/vx_join` 分歧控制。

设备把并行线性层调用数写入 `report[9]`，线程数、实际参与线程数和 warp 数写入
`report[10..12]`，每线程完成的输出列数写入 `report[128+tid]`。
CPU 回读真实字节，Python 参考独立推导并核对这些计数，同时校验所有模型中间值与生成 token。
默认输入 `"red "` 生成 `"blu"`、token ID `[4,10,15]`，完成 42 次线性层调用；
各线程输出列数为 `[60,54,54,54,54,54,54,54]`。

实际周期和通过结论以本次运行报告与 `summary.json` 为准。

## 本次验收结果（2026-10-08）

运行编号 `test-20261008-173856`，完整平台回归通过。平台构建后重新编译当前 LLM，
使用 `third_party/gem5/runtime/test.py` 执行与 `./build.sh --test` 相同的完整回归后端。
默认 SMOKE 和默认 LLM 各运行一次，19 项原生内存测试、在线 C ABI、29 项错误拒绝检查通过。

| 默认场景 | 输出 | GPU 周期 | GPU HETTrace 事务 | 实际 CPU 核 | 归档摘要 |
|---|---|---:|---:|---:|---|
| SMOKE | `42` | 863 | 267 | 4 | [查看](summary.json) |
| LLM | `blu`，ID `[4,10,15]` | 225771 | 3148 | 4 | [查看](summary.json) |

默认参数为 GPU 1000 MHz、2 核 × 4 warp × 4 lane；CPU 四核、2000 MHz；
HBM4 八通道、AXI 2 ns、KV cache 启用。
本次 LLM 的一个工作组实际在 GPU 核 0 执行，8 个线程、2 个 warp 参与线性层计算。
实际线性层调用数为 42，各线程输出列数为 `[60,54,54,54,54,54,54,54]`。
GPU 的配置容量与这次使用的线程／核数量分别记录，不用配置值代替实际工作量。

权重、KV、全部阶段中间值、生成 token、线程工作量、真实回读字节、
AXI／Flit／MEMSIM／DFI／VCD 检查通过。最大中间值绝对误差约 `3.42e-06`，在本次误差容限内。
这些数字属于 gem5 + Vortex SimX 仿真，包含程序和观测记录开销。

归档证据：[回归摘要](summary.json)、[LLM 数值与线程摘要](llm_summary.json)、
[CPU 实际执行](host_summary.json)、[输入配置](input.json)、
[设备反汇编](program.dis)、[源码基线与文件大小](source_version.json)。
本次使用工作区修改；完整源码快照、波形、Flit 和内存记录保存在对应的用户结果目录中。
