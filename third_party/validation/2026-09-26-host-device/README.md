# CPU/GPU 程序拆分与 gem5 多核验收

每个用户项目显式包含 `host.cpp`、`kernel.cpp`。主机使用 gem5 x86 CPU 执行，设备使用 Vortex SimX 执行 RV32 程序；Makefile 分别声明两类源码。实际构建记录位于每次结果的 `build/programs.json`，对应源码快照在 `build/sources/`。

## 实际结果

| 场景 | 输出 | 活跃 CPU 核 | GPU 周期 | 核对 |
|---|---|---:|---:|---|
| smoke | 42 | 4 | 863 | [PASS](cases/smoke/summary.json) |
| smoke_slow | 42 | 4 | 1492 | [PASS](cases/smoke_slow/summary.json) |
| smoke_wrap | 0 | 4 | 863 | [PASS](cases/smoke_wrap/summary.json) |
| smoke_cpu2 | 42 | 2 | 1139 | [PASS](cases/smoke_cpu2/summary.json) |
| llm | blu | 4 | 349069 | [PASS](cases/llm/summary.json) |
| llm_no_cache | blu | 4 | 827005 | [PASS](cases/llm_no_cache/summary.json) |
| llm_replay | blu | 4 | 349037 | [PASS](cases/llm_replay/summary.json) |
| llm_long | blue | 4 | 761135 | [PASS](cases/llm_long/summary.json) |
| smoke_arch | 42 | 2 | 1259 | [PASS](cases/smoke_arch/summary.json) |
| tutorial_smoke | 42 | 4 | 863 | [PASS](cases/tutorial_smoke/summary.json) |
| custom_project | 2 words matched | 4 | 735 | [PASS](cases/custom_project/summary.json) |

活跃核由实际提交指令数判定；内置 SMOKE/LLM 还检查每核 L1 访问、MMU 样本、准备/检查阶段的完整线程分片和不同线程 ID。例子使用屏障同时集合线程，默认主线程加三个工作线程。CPU 负责输入准备和结果检查，GPU 负责设备计算。

默认 SMOKE 四核的提交指令数为 [2372814, 38287, 8220, 6215]；两核对照为 [2356535, 38780]。两种配置均产生 42。短示例的线程启动和同步开销较明显，核数与实际执行核数可以核对，不据此宣称线性加速。

TinyLLM 输出、权重、KV、中间结果和 token 均通过独立参考核对；KV cache 开/关的前向次数为 6/15。所有平台场景均完成 AXI CSV/VCD、Flit 和在线内存检查。19 项原生测试、在线 C ABI 及 26 项错误拒绝通过。新增错误拒绝覆盖空闲 CPU、缺失工作线程、重复线程 ID 和错误任务分片。

## 执行与复现

首批三个场景受到运行中修改 shell 提示文字的影响，入口返回失败，原失败记录保留。修复后的脚本已在新目录重跑这些场景；本记录仅汇总最终成功的执行。教程项目与自定义项目执行后归档到内部缓存。

```bash
./build.sh --test
```

该入口包含本次九组平台配置。用户可在 `user/` 运行 `./run.sh smoke`、`./run.sh llm`，结果会列出每核统计和 CPU/GPU 程序来源。精简机器记录见 [summary.json](summary.json)；原始波形保存在各记录的 `raw_result_directory`（相对于本验收目录）。
