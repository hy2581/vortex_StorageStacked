# 内部维护

用户入口为根目录 build.sh 和 user/run.sh；配置在 user/<项目>/config.json。
third_party/ 提供 gem5、Vortex、SDK、工具与验证；integration/ 负责 gem5/TLM 到公共 AXI 存储的接入。
只用 gem5 自带的一套 SystemC，1 fs 时间基准，保留真实异步响应、字节掩码、反压与在线内存反馈。
不得以退出码或文件存在代替计算、AXI/VCD、Flit、MEMSIM 验收。
禁止 submodule，不生成摘要算法清单。配置与报告使用相对路径，内部缓存由 build.sh 重建。
根目录 ./build.sh --test 执行回归。只有得到用户明确授权才上传。
