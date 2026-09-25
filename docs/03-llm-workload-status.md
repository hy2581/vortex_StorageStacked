# 3. 当前 LLM 基础算子做了什么，在哪里完成

核对日期：2026-09-25。范围仅为当前 `vortex_StorageStacked` 工程。

本项目按“部署几个常见算子”的范围接入负载：在原有矩阵乘法 SGEMM 之外，增加矩阵向量乘 SGEMV、Softmax 和 ReLU。它们使用官方运行库和真实 GPU 内核，经过完整的在线访存链路，主机取回结果后独立验算。

这里测的是单个基础算子的计算和数据传输。没有加载某个训练好的语言模型，也没有实现文本分词、整模型多层推理、KV cache 或逐 token 生成流程。

## 一、可以运行哪些算子

| 算子 | 通俗解释 | 本项目预设规模 | 与模型计算的关系 |
|---|---|---|---|
| `sgemm` | 两个矩阵相乘 | 4×4 乘 4×4 | 基础线性代数运算 |
| `sgemv` | 一个矩阵乘一个向量 | 8×8 矩阵乘 8 元素向量 | 可对应单个输入向量的线性变换 |
| `softmax` | 把一行分数变成非负、总和为 1 的值 | 8×8，逐行处理 | 可用于注意力分数等归一化计算 |
| `relu` | 负数变成 0，非负数原样保留 | 16 元素向量 | 基础激活函数算例，未指定某个模型的激活结构 |

这些算子都是 FP32 浮点负载，输入是可复现的测试数据。规模较小，目的是把数值正确性和完整链路验收做清楚；它们的周期不能直接换算成某个 LLM 的 tokens/s 或首 token 延迟。

## 二、每个算子具体做什么

### 1. SGEMM：矩阵乘法

GPU 线程根据行、列坐标计算一个输出元素：

```text
C[row,col] = A[row,0]×B[0,col] + A[row,1]×B[1,col] + …
```

主机生成随机 A、B，上传数据，启动 GPU 内核，再读回 C。主机的 `matmul_cpu()` 另算一份参考矩阵，逐项比较。

源码：[主机程序](../third_party/vortex/tests/regression/sgemm/main.cpp)、[GPU 内核](../third_party/vortex/tests/regression/sgemm/kernel.cpp)。

### 2. SGEMV：矩阵向量乘法

每个 GPU 线程负责矩阵的一行，把这一行与输入向量逐项相乘再求和：

```text
y[row] = A[row,0]×x[0] + A[row,1]×x[1] + …
```

当前沿用上游一次处理 4 列的 `float4` 内核，因此统一配置要求 `elements` 为 4 的倍数。为了保持使用方式简单，本项目令行数和列数都等于 `elements`，启动时同时传入 `-m` 和 `-n`。

本项目给输入加入正负值，CPU 用独立的逐元素循环计算参考输出，并检查 GPU 输出是否有限、误差是否在范围内。每个输出允许的误差为 `1e-4 + 1e-5 × |参考值|`。

源码：[主机生成与验算](../third_party/vortex/tests/regression/sgemv/main.cpp)、[GPU 内核](../third_party/vortex/tests/regression/sgemv/kernel.cpp)。

### 3. Softmax：逐行归一化

每个 GPU 线程处理一行，执行三步：

1. 找到该行最大值 `m`。
2. 计算每项的指数近似 `exp(x[i] - m)`，同时求和。
3. 用每项指数值除以总和，写出结果。

先减最大值，可以避免很大的正数直接求指数导致溢出。输入缓冲区会临时保存指数值，因此设备端输入区域使用读写权限；输出另存到目标缓冲区。

上游算例原本直接使用自定义多项式近似指数，并将最大值初始化为 0。本项目从该行首元素开始寻找最大值，适用于全负分数和带大偏移的输入；也移除了原算例中未参与计算的第二个输入缓冲区。

GPU 指数函数在 `exp.h` 中实现：先把输入拆成 `k × ln(2) + r`，让 `r` 落在接近 0 的小范围内，再用七次多项式计算 `exp(r)`，最后乘回 `2^k`。全程使用 FP32；小于 -80 的值置零，丢掉的指数值小于 `2×10⁻³⁵`。这是针对 Softmax 非正输入的数值近似，不是通用数学库的精确舍入实现。

接入时曾尝试直接调用工具链 `expf`，但实际 GPU 结果未通过独立验算。该路径会调用软件双精度函数，其库内故障点尚未确定；当前算子改用上述明确范围的 FP32 实现，未放宽输出验算标准。

当前测试数据覆盖全为 -1000 的行、1000 附近的正数行、80/-80 的强对比行，以及普通正负混合行。主机保留原始输入，使用双精度 `std::exp` 独立计算参考结果，并检查：

- 每项输出有限、非负且不大于 1。
- 每项误差不超过 `2e-6 + 2e-5 × |参考值|`。
- 每一行的输出和与 1 的误差不超过 `2e-5`。

源码：[主机输入与双精度验算](../third_party/vortex/tests/regression/softmax/main.cpp)、[GPU 内核](../third_party/vortex/tests/regression/softmax/kernel.cpp)、[FP32 指数近似](../third_party/vortex/tests/regression/softmax/exp.h)、[共享参数结构](../third_party/vortex/tests/regression/softmax/common.h)。

### 4. ReLU：负数置零

GPU 的每个线程处理一个元素：

```text
y[i] = x[i] < 0 ? 0 : x[i]
```

本项目使用 `-1000、-7、-1、0、1、3、7、1000` 的重复序列。16 元素预设能同时覆盖负数置零、零输入和正数保留，避免只用正数时把 ReLU 测成一次数据复制。

主机逐项检查结果有限且与参考值完全相等。GPU 内核还增加了线程索引边界检查，避免末尾多出来的线程访问向量之外。

源码：[主机输入与验算](../third_party/vortex/tests/regression/relu/main.cpp)、[GPU 内核](../third_party/vortex/tests/regression/relu/kernel.cpp)。

## 三、这些事情分别在哪里做

“主机”有两层含义：算例里的主机程序运行在 **gem5 模拟的 x86 CPU** 上；启动仿真及事后检查的 Python 脚本运行在 **实际 Linux 主机** 上。

| 工作 | 执行位置 | 主要代码 |
|---|---|---|
| 生成输入、分配缓冲区、提交任务 | gem5 中的 x86 主机 | 各算子的 `main.cpp` |
| 管理任务队列、安排上传和启动 | 官方运行库与 CP | [运行库](../third_party/vortex/sw/runtime/)、[命令处理器](../third_party/vortex/sim/common/cmd_processor.cpp) |
| 矩阵乘加、指数、归一化、ReLU | Vortex SimX 执行 GPU 指令 | 各算子的 `kernel.cpp` |
| 将外部读写发给 gem5，接收完成事件 | Vortex 的 gem5 设备适配 | [vortex_gpgpu_dev.cc](../integration/dev/vortex/vortex_gpgpu_dev.cc) |
| TLM、AXI、Flit、UCIe 数据传输 | 本项目链路模型 | [gem5_axi](../gem5_axi/)、[axi2flit](../axi2flit/)、[ucie-model](../ucie-model/) |
| 保存设备数据、模拟内存访问和时序 | 在线 mem_sim | [公共 mem_sim](https://github.com/hy2581/axi_StorageStacked/blob/main/mem_sim/) |
| 读回输出、执行独立参考计算 | gem5 中的 x86 主机 | 各算子的 `main.cpp` |
| 核对数值报告、协议、内存和波形 | 实际 Linux 主机 | [validate.py](../scripts/validate.py)、[verify.py](../scripts/verify.py) |

算子的乘加、指数等运算由 SimX 中的 GPU 指令完成；mem_sim 负责数据存储和响应时序。主机程序和栈使用独立本地主存，GPU BAR 的上传/下载、核心及 CP 的外部读写经过完整在线链路。

## 四、一次运行从哪里进入

流程是：选择 `config/benchmarks/` 下的算例 → `run.py` 解析并检查构建状态 → gem5 启动官方主机程序 → 运行库提交 GPU 内核 → 读回并验算 → Python 检查完整链路。

同一 GPU 配置的构建会生成全部已接入算例。生成的主机程序和 `kernel.vxbin` 分别位于 `build/vortex/tests/regression/sgemv/`、`softmax/`、`relu/` 等目录，运行入口只使用本项目的这些产物。

```bash
./run.sh config --benchmark config/benchmarks/sgemv.json
./run.sh run --benchmark config/benchmarks/sgemv.json

./run.sh config --benchmark config/benchmarks/softmax.json
./run.sh run --benchmark config/benchmarks/softmax.json

./run.sh config --benchmark config/benchmarks/relu.json
./run.sh run --benchmark config/benchmarks/relu.json
```

默认 `./run.sh run` 仍运行 vecadd；上面的 `--benchmark` 为本次运行选择算子。也可在 `config/run.toml` 的 `[benchmark]` 中填写同样的名称和规模，设为日常默认值。参数含义见 [第二篇](02-configuration-and-benchmarks.md)。

## 五、怎么看算子与链路是否都通过

三个新增算例会在 `run.log` 输出一行 `LLM_CHECK` 数值检查报告。检查器要求算子名称、规模和输出数量与本次配置一致，再将报告写进 `summary.json` 的 `operator_check`。

- SGEMV 报告行列数、已检查输出数和最大绝对误差。
- Softmax 报告已检查输出数、最大绝对误差和最大行和误差。
- ReLU 报告已检查输出数，以及负数、零和正数输入各有多少个。

这些数值检查之后，还必须通过实际 AXI 五通道、Flit 顺序、内存请求/返回和波形检查。只看到 `PASSED!`、正常退出或生成了输出文件，都不能单独作为完整链路验收。

完整命令为 `./run.sh test`，当前包括 8 个端到端场景：默认、慢内存、CRC 重放、另一向量规模、SGEMM、SGEMV、Softmax、ReLU。此外，[check_softmax_exp.cpp](../scripts/check_softmax_exp.cpp) 会在主机上扫描 1,000,001 个指数输入点，结果保存为 `softmax-exp-check.json`；这一检查不能代替 GPU 输出和完整链路检查。

本轮算子的实际计算结果如下，使用默认 1 核、每核 4 个 warp、每 warp 4 线程和 HBM4 配置：

| 算子 | GPU 周期 | 核心 + CP 完成请求数 | 主机数值验算 |
|---|---:|---:|---|
| [SGEMM，4×4](../validation/2026-09-25-llm/sgemm/summary.json) | 1450 | 98 | 官方主机逐项比较通过 |
| [SGEMV，8×8](../validation/2026-09-25-llm/sgemv/summary.json) | 1716 | 132 | 8 项全部通过；最大绝对误差约 `5.96×10⁻⁸` |
| [Softmax，8×8](../validation/2026-09-25-llm/softmax/summary.json) | 7418 | 110 | 64 项全部通过；最大绝对误差约 `1.78×10⁻⁸`，最大行和误差约 `3.45×10⁻⁸` |
| [ReLU，16 元素](../validation/2026-09-25-llm/relu/summary.json) | 885 | 91 | 16 项完全相等；覆盖 6 个负数、2 个零、8 个正数 |

表中请求数是 SimX 核心和 CP 的原生请求数，不是主机上传数量，也不是 AXI burst 或 Flit 数。

本轮结果目录为 `results/acceptance-llm-fp32-20260925/`，19 项原生内存测试、在线 C ABI、指数扫描和 8 个端到端场景已全部通过。[验收记录](../validation/2026-09-25-llm/README.md) 保存了摘要和实际主机日志，完整波形、Flit 和内存证据保留在结果目录中。

首次接入的失败记录保留在 `results/acceptance-llm-20260925/`，其中的总汇总不作为通过记录。

## 六、当前负载的范围

这是一组独立算子负载，能验证真实计算和外部内存响应对执行的影响。它没有把各算子串成完整注意力层或语言模型，没有训练权重、文本输入输出或 KV cache，也没有模型级推理性能结论。

当前 GPU 使用 SimX C++ 功能/周期模型，内存使用行为模型。算子验收证明的是已运行规模和配置下的数值与链路正确性；其他规模、其他 GPU 参数，以及真实芯片的绝对性能需要各自的验证。
