# gem5 来源与集成扩展

上游版本记录见 [sources.json](../runtime/defaults/sources.json) 与 [.source-version](../.source-version)，许可证见 [LICENSE](../LICENSE)。
本目录保留 gem5 的 DMA 字节掩码、掩码写入和 VCD 时间处理补丁。设备 timing 回调、跟踪接口和平台构建支持随当前源码交付；补丁文件用于保留改动依据，构建直接使用已集成的源码。

`../runtime/` 提供本平台的环境、构建、运行与校验脚本；用户入口为仓库根目录 `build.sh` 和 `user/run.sh`。Vortex 的来源说明见 [Vortex 补丁记录](../../vortex/patches/README.md)。

运行侧对同一外部存储块的读写冲突等待真实完成，保留异步链路中的访问顺序；验收按事务时刻独立检查。
