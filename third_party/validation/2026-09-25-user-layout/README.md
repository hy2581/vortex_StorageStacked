# 用户目录重构验收（2026-09-25）

本记录来自重构后重新编译与实际执行。7 组默认平台回归通过后，另行执行 1 组硬件参数变更；共 8 组平台场景。另按用户文档从零创建项目，执行 SMOKE 和 custom 两次验证。机器可读汇总见 [summary.json](summary.json)。

| 场景 | 实际输出 | GPU 周期 | AXI 握手数 | 记录 |
|---|---|---:|---:|---|
| smoke | 42 | 1150 | 28458 | [PASS](cases/smoke/summary.json) |
| smoke_slow | 42 | 2212 | 28458 | [PASS](cases/smoke_slow/summary.json) |
| smoke_wrap | 0 | 1059 | 28427 | [PASS](cases/smoke_wrap/summary.json) |
| llm | blu | 412691 | 57880 | [PASS](cases/llm/summary.json) |
| llm_no_cache | blu | 867871 | 78838 | [PASS](cases/llm_no_cache/summary.json) |
| llm_replay | blu | 416701 | 57880 | [PASS](cases/llm_replay/summary.json) |
| llm_long | blue | 823153 | 74254 | [PASS](cases/llm_long/summary.json) |
| smoke_arch | 42 | 1310 | 28662 | [PASS](cases/smoke_arch/summary.json) |
| tutorial_smoke | 42 | 1150 | 28458 | [PASS](cases/tutorial_smoke/summary.json) |
| custom_project | 1 word matched | 827 | 28372 | [PASS](cases/custom_project/summary.json) |

默认 SMOKE 为 41 → 42，溢出场景为 0xffffffff → 0。默认 TinyLLM 为 `red ` → `blu`，长提示词为 `red blue ` → `blue`。KV cache 开启/关闭分别执行 6/15 次位置计算，并保持生成 token 相同。慢内存使默认 SMOKE 的 GPU 周期由 1150 增至 2212。

硬件变更场景使用 2 个 CPU 核、32 项 TLB、16 KiB L1 与 512 KiB L2；GPU 为 4 核、8 warp、8 线程、32 KiB L1、启用 512 KiB L2；AXI 为 3 ns、2 个在途请求、1 平面；UCIe 为 8 lanes、16 GT/s、80 ns TAT；内存延迟倍率 2、队列/槽位各 1、响应保持 3。每组记录保存实际输入、实际 UCIe 配置和 MMU 采样。

所有场景均通过计算结果、实际内存回读、AXI CSV/VCD、Flit、在线 MEMSIM 与 DRAM/DFI 核对。重放场景注入 CRC 错误并检查重放完成和最终数据；这类预期注入计数保留在结果中。

附加验证：19 项原生测试、在线 C ABI、22 项配置/输出错误拒绝、3 项入口错误拒绝，以及 1,000,001 点 FP32 exp 数值扫描通过。LLM 默认逐项核对 1126 个 KV/中间值，最大绝对误差约 3.42e-6。

源码导出到另一个目录后，检查了目录结构、入口、相对路径与源码版本；该导出目录没有再次执行完整平台编译。上表实际执行发生在当前工作区。

复现整体测试：

```bash
./build.sh --test
```

当前回归入口已包含硬件参数变更场景。新增结果位于 `user/<项目>/result/`，测试汇总位于 `third_party/.cache/validation/`。本目录保留精简验收结果；大型原始波形和事务文件保留在本地运行结果中。案例 JSON 的 `raw_result_directory` 相对于本目录。教程项目执行后归档至内部缓存。
