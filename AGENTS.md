# vortex_StorageStacked

先读 README.md、config/README.md。仅维护本驱动和显式声明的 axi_StorageStacked 依赖；禁止加载另一驱动的源码或二进制。
唯一生产运行链路是 vortex → gem5 timing → AXI256 → AXI2Flit → UCIe → 在线 mem_sim。
只用 gem5 自带 SystemC、全局 1fs。配置统一放 config/。
不得用伪造 trace、测试 RAM、退出码或文件存在替代计算和链路验收。
验收命令 ./run.sh test；单例 ./run.sh run。保留新的结果目录和五通道/Flit/内存证据。
所有交付不计算、展示或要求摘要算法；使用版本、文件名/大小、实际运行结果。
不得 push，除非用户明确授权。
