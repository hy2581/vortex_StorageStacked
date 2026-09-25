# 官方 Vortex benchmark

运行源位于 `third_party/vortex/tests/regression/`：`vecadd`、`sgemm`、`sgemv`、`softmax`、`relu`。
保留官方运行库和算例组织方式；本项目对新增算子的输入、数值检查及 Softmax 指数实现做了适配。
选择与规模统一配置在 `config/run.toml` 的 `[benchmark]` 小节，产物在 `build/vortex/tests/regression/`。
具体操作见 [参数与 benchmark 说明](../docs/02-configuration-and-benchmarks.md)。
新增算子的计算位置和实现细节见 [LLM 算子说明](../docs/03-llm-workload-status.md)。
