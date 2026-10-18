# 结果格式与离线报告

格式版本为 `local-benchmark-result-1`。字段模板见 `examples/result-template.json`。

## 必需元数据

- `suite_version`、`suite_sha256`：公开题库文件原始字节的SHA-256；不能随意复用旧哈希。
- `batch_id`、`hardware_id`：同一顺序批次与同一设备的非个人化代号。不填账号名、序列号或本地路径。
- `contract`：运行器版本、参数/工具合同代号、模型总时限、单题诊断上限。使用相同代号时仍须保留实际合同说明。
- `model`：精确标签、指纹、量化、模板哈希；用本地适配器读取，不从名字猜测。
- `data_kind`：真实测评为`measured`；虚构报告演示为`demo`。本包空白模板是demo。
- `run_status`：`completed`、`invalid_runtime`、`invalid_budget`、`incomplete`之一。后三种不进入正式排名。
- `tasks`：F01、F02、C01、C02、C03、T01、T02、D01恰好各一项。状态为`completed`、`not_run`或`invalid_runtime`，质量得分是原始分，耗时为累计模型调用秒数。
- 每项 `evidence` 写证据摘要或本地证据记录ID，不能填空泛“通过”。不写个人资料或绝对路径。报告只展示聚合值，不展示答案。
- D01的 `review` 含`facts`（0–12）、`blind`（0–8）、`cap`（null或0–20）、`locked`。最终D01分应等于两者之和，若有明确cap则取上限；争议另行记录。
- `hard_failures` 是失败类别代号列表，不含原始敏感内容。即使有完整分数，报告也不为其推荐自动执行。

## 门禁

严格拒绝缺题、重复题、超范围分数、负数/非有限耗时、布尔伪装数字、缺少元数据或不同合同混排。空白模板允许保存和结构验证，但不应被称作有效实测。

真实结果必须有已完成运行、八道已完成任务、逐题证据、D01锁分，且累计时间未超合同上限。硬失败可保留排名可见性，但必须单列并阻止部署结论。没有完整运行的候选只列原因。

## CLI

```bash
python3 local-model-benchmark/scripts/report.py template --output run.json
python3 local-model-benchmark/scripts/report.py validate run.json
python3 local-model-benchmark/scripts/report.py report run-a.json run-b.json --output comparison.md
```

输入输出必须位于当前工作目录，使用相对路径；脚本拒绝符号链接和上级路径，不覆盖已有输出。使用示例分数测试报告时必须额外指定`--allow-demo`，而且不能把demo与measured混在一张榜单。

`validate`会分别返回结构有效性与是否可排名。`report`只在同题库、合同、设备与批次内分别给质量榜和用时榜；未锁分/无效运行单独列出，没有自动部署或替换动作。
