# Local Model Benchmark Skill

用一套固定任务，比较本地模型答得是否准确、完成得是否够快，以及复测结果是否稳定。

## 功能

- 8道合成任务，覆盖推理、编程、工具调用和文档证据分析。
- 质量按100分评分；回答质量与用时分开排名。
- 提供复核规则、结果模板，以及离线校验和报告脚本。

这是测评方法和结果工具，不负责启动模型或搭建执行环境。测评时需要已有的本地模型接口；编程任务还需要隔离执行环境。工具脚本只校验结果并生成报告。

## 下载与安装

从 [Releases](https://github.com/patmenciu/local-model-benchmark-skill/releases) 下载 ZIP。解压后，将其中的 `local-model-benchmark/` 文件夹放入 Agent 的技能目录。

调用示例：

> 使用 $local-model-benchmark，按合成题库比较我已安装的本地模型，分别汇报质量、用时和复测稳定性。

## 测评范围

| 模块 | 内容 | 分值 |
|---|---|---:|
| 基础推理 | 分母核验、依赖关系 | 15 |
| 编程工程 | 接口实现、缺陷修复、仓库读改测 | 40 |
| 工具调用 | 只读恢复、确认写入与核验 | 25 |
| 文档证据 | 跨材料事实、条件与未知项 | 20 |

各模型使用相同设备、题库、运行合同和顺序批次。默认保留模型原生设置。单轮结果用于初筛；模型替换或高影响用途应再做一轮独立复测。运行时限内未完成的任务单独标注，不作为完整低分结果。

## 运行要求

- 已安装 Python 3.10 或更新版本；无需第三方依赖。
- 只测试本机已安装的模型。模型版本、量化或运行后端变化后，应重新确认结果是否可比。
- 只对实际运行的能力给出结论。视觉、音频、结构化输出和工具调用需分别按对应任务测试。

## 离线工具

```bash
python3 local-model-benchmark/scripts/report.py template --output run.json
python3 local-model-benchmark/scripts/report.py validate run.json
python3 local-model-benchmark/scripts/report.py report run-a.json run-b.json --output comparison.md
```

模板需要填入实际运行记录和复核结果后，才能用于正式比较。脚本不会运行模型或覆盖已有文件；输入输出路径需位于当前工作目录。

## 结果说明

公开题库版本为 `public-synthetic-1`，任务材料均为虚构内容。它适合对照同一版本和合同下的结果，不代表通用能力总榜。示例模板中的模型和硬件值仅供填写格式参考。离线测试验证的是报告工具，不代表模型运行、代码隔离或真实业务安全已经验证。

版本：`1.1.1`。技术说明见 [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md)。
