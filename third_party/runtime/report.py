"""One human report derived from the acceptance summary."""
import json
from paths import dump

def write_report(root):
    s=json.loads((root/'summary.json').read_text());lines=['# Vortex 运行报告','']
    if not s.get('passed'):
        lines+=['**未通过验收**', '', '阶段：'+s.get('stage','unknown')]
        if s.get('error'):lines+=['','```text',s['error'],'```']
    elif 'cases' in s:
        lines+=['**PASS** — 设备场景与错误拒绝检查通过。','','| 场景 | 输出 | GPU 周期 | 报告 |','|---|---|---:|---|']
        for name,c in s['cases'].items():lines.append(f"| {name} | {c['output']} | {c['cycles']} | [查看]({c['report']}) |")
    else:
        a=json.loads((root/'resolved.json').read_text())['architecture'];b=s['benchmark']
        lines += [f"**PASS** — {b['name'].upper()} 计算、AXI 五通道、Flit、在线内存和波形核对通过。",'',
          f"CPU {a['host']['num_cpus']} 核 / {a['host']['clock_mhz']} MHz；GPU {a['simx']['cores']} 核 × {a['simx']['warps']} warp × {a['simx']['threads']} 线程 / {a['device_clock_mhz']} MHz。",'',
          f"CPU L1I/L1D/L2：{a['host']['l1i']} / {a['host']['l1d']} / {a['host']['l2']}；每核 ITLB、DTLB 各 {a['host']['tlb_entries']} 项。",'',
          f"AXI 256 bit / {a['axi']['period_ns']} ns；UCIe {a['ucie']['lanes']} lanes × {a['ucie']['rate_gtps']} GT/s；{a['memory']['standard'].upper()} × {a['memory']['channels']} 通道，时序倍率 {a['memory']['scale']}。",'',
          f"GPU 周期：{s['devices']['cycles']}；GPU 外部事务：{s['sources']['vortex']['transactions']}；主机外部事务：{s['sources']['host']['transactions']}。",'']
        if 'smoke' in s:
            r=s['smoke'];lines+=[f"输入 **{r['input']}** → 加一 → 输出 **{r['output']}**；{r['workers']} 个工作组全部与独立期望一致。",'']
        if 'llm' in s:
            r=s['llm'];lines += [f"输入 `{json.dumps(r['prompt'],ensure_ascii=False)}` → 生成 `{r['generated_text']}`；token ID：{r['generated_token_ids']}。",'',
              f"{r['model_parameters']} 个参数；KV cache={r['kv_cache']}；前向位置计算 {r['forward_calls']} 次。权重、KV、中间结果、token 和完成状态已逐项核对。",'',
              '数值核对见 [llm_summary.json](llm_summary.json)。','']
        if 'custom' in s:lines+=['自定义输出字均与配置中的期望值一致。','']
        lines+=['地址转换见 [mmu_translations.csv](mmu_translations.csv)，缓存/TLB 统计见 [soc_summary.json](soc_summary.json)。', '',
                '链路视图：[memsim_view.html](memsim_view.html)；实际配置：[resolved.json](resolved.json)。', '',
                '原始证据：axi_wave.vcd、axi_events.csv、ucie_flits.csv、memsim_bridge.csv、hettrace/。所有周期与延迟均为仿真值。']
    lines+=['','最终状态与各项核对：[summary.json](summary.json)。','']
    (root/'report.md').write_text('\n'.join(lines))
def write_status(root,stage,error=None):
    s={'passed':False,'stage':stage}
    if error is not None:s['error']=str(error)
    dump(root/'summary.json',s);write_report(root)
