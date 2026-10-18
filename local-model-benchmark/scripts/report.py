"""Offline result gates and rankings. Does not run models or generated code."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from path_guard import workspace_root, file_path, write_new

POINTS = {'F01': 7, 'F02': 8, 'C01': 10, 'C02': 12, 'C03': 18, 'T01': 12, 'T02': 13, 'D01': 20}
MODULES = {'基础': ('F01', 'F02'), '编程': ('C01', 'C02', 'C03'), '工具': ('T01', 'T02'), '文档': ('D01',)}
PACKAGE_ROOT = workspace_root(Path(__file__).absolute().parents[1])


def read_json(root, relative):
    def reject_constant(_):
        raise ValueError('non-finite JSON number')
    return json.loads(file_path(root, relative).read_text(encoding='utf-8'), parse_constant=reject_constant)


def number(value, low=0, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('numeric field must be finite')
    if value < low or (high is not None and value > high):
        raise ValueError('numeric field outside allowed range')
    return float(value)


def label(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise ValueError('missing or invalid ' + field)
    if value.startswith('/') or any(ord(char) < 32 for char in value) or any(c in value for c in '\\<>|[]()!`*'):
        raise ValueError('invalid label characters')
    return value


def mapping(value, field):
    if not isinstance(value, dict):
        raise ValueError(field + ' must be an object')
    return value


def validate(value):
    run = mapping(value, 'result')
    if run.get('schema_version') != 'local-benchmark-result-1':
        raise ValueError('unsupported schema')
    if run.get('suite_version') != 'public-synthetic-1':
        raise ValueError('unsupported question set')
    digest = run.get('suite_sha256')
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise ValueError('invalid question set hash')
    canonical_digest = hashlib.sha256(file_path(PACKAGE_ROOT, 'examples/synthetic-tasks.json').read_bytes()).hexdigest()
    if digest != canonical_digest:
        raise ValueError('question set hash does not match this package')
    for key in ('batch_id', 'hardware_id'):
        label(run.get(key), key)
    if run.get('data_kind') not in ('measured', 'demo'):
        raise ValueError('invalid data kind')
    if run.get('run_status') not in ('completed', 'invalid_runtime', 'invalid_budget', 'incomplete'):
        raise ValueError('invalid run status')
    contract = mapping(run.get('contract'), 'contract')
    if set(contract) != {'runner_version', 'settings_id', 'model_limit_seconds', 'request_limit_seconds'}:
        raise ValueError('incomplete or unknown contract fields')
    label(contract.get('runner_version'), 'runner version')
    label(contract.get('settings_id'), 'settings id')
    limit = contract.get('model_limit_seconds')
    if limit is not None:
        number(limit, low=0.001)
    if contract.get('request_limit_seconds') is not None:
        number(contract['request_limit_seconds'], low=0.001)
    model = mapping(run.get('model'), 'model')
    for key in ('tag', 'fingerprint', 'quantization', 'template_hash'):
        label(model.get(key), 'model ' + key)
        if run['data_kind'] == 'measured' and model[key].startswith('example-'):
            raise ValueError('replace example model metadata')
    tasks = run.get('tasks')
    if not isinstance(tasks, list) or len(tasks) != len(POINTS) or any(not isinstance(t, dict) for t in tasks):
        raise ValueError('exactly eight task objects are required')
    ids = [t.get('id') for t in tasks]
    if any(not isinstance(i, str) for i in ids) or set(ids) != set(POINTS) or len(set(ids)) != len(ids):
        raise ValueError('missing, repeated or unknown task')
    reasons = []
    if run['run_status'] != 'completed':
        reasons.append('运行未完成或无效')
    by_id = {}
    for task in tasks:
        task_id = task['id']
        by_id[task_id] = task
        if task.get('status') not in ('completed', 'not_run', 'invalid_runtime'):
            raise ValueError('invalid task status')
        number(task.get('score'), high=POINTS[task_id])
        number(task.get('model_seconds'))
        evidence = task.get('evidence')
        if not isinstance(evidence, list) or any(not isinstance(item, str) or not item.strip() for item in evidence):
            raise ValueError('invalid task evidence')
        if task['status'] != 'completed':
            reasons.append(task_id + '未完成')
        if not evidence:
            reasons.append(task_id + '缺证据')
    review = mapping(by_id['D01'].get('review'), 'document review')
    facts = number(review.get('facts'), high=12)
    blind = number(review.get('blind'), high=8)
    cap = review.get('cap')
    if cap is not None:
        number(cap, high=20)
    if not isinstance(review.get('locked'), bool):
        raise ValueError('review locked must be boolean')
    expected = min(facts + blind, cap) if cap is not None else facts + blind
    if not math.isclose(by_id['D01']['score'], expected, abs_tol=0.000001):
        raise ValueError('document score disagrees with review')
    if not review['locked']:
        reasons.append('文档未锁分')
    hard = run.get('hard_failures')
    if not isinstance(hard, list):
        raise ValueError('hard failures must be a list')
    for failure in hard:
        label(failure, 'failure code')
    total_seconds = sum(t['model_seconds'] for t in tasks)
    if limit is not None and total_seconds > limit:
        reasons.append('累计调用超预算')
    return {
        'rankable': not reasons,
        'reasons': list(dict.fromkeys(reasons)),
        'tag': model['tag'],
        'score': round(sum(t['score'] for t in tasks), 2),
        'seconds': total_seconds,
        'modules': {name: round(sum(by_id[k]['score'] for k in keys), 2) for name, keys in MODULES.items()},
        'hard_failures': hard,
    }


def new_template():
    value = read_json(PACKAGE_ROOT, 'examples/result-template.json')
    raw = file_path(PACKAGE_ROOT, 'examples/synthetic-tasks.json').read_bytes()
    value['suite_sha256'] = hashlib.sha256(raw).hexdigest()
    return value


def comparison_key(run):
    return (run['schema_version'], run['suite_version'], run['suite_sha256'], run['batch_id'], run['hardware_id'], json.dumps(run['contract'], sort_keys=True), run['data_kind'])


def md_cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def report(runs, *, allow_demo=False):
    if len(runs) < 2:
        raise ValueError('provide at least two configurations')
    summaries = [validate(r) for r in runs]
    if len({comparison_key(r) for r in runs}) != 1:
        raise ValueError('question set, contract, batch, device or data kind differs')
    if runs[0]['data_kind'] == 'demo' and not allow_demo:
        raise ValueError('demo results require --allow-demo')
    identities = [(r['model']['tag'], r['model']['fingerprint'], r['model']['template_hash']) for r in runs]
    if len(set(identities)) != len(identities) or len({s['tag'] for s in summaries}) != len(summaries):
        raise ValueError('duplicate configuration or ambiguous model label')
    valid = [s for s in summaries if s['rankable']]
    invalid = [s for s in summaries if not s['rankable']]
    title = '# 本地模型测评对比' + ('（纯虚构报告演示，不是实测）' if runs[0]['data_kind'] == 'demo' else '')
    lines = [title, '', '同题库、同合同、同设备、同顺序批次。质量与累计模型回答用时分别排列。', '', '## 质量', '', '| 模型 | 总分/100 | 基础/15 | 编程/40 | 工具/25 | 文档/20 | 硬失败 |', '|---|---:|---:|---:|---:|---:|---:|']
    ordered = sorted(valid, key=lambda s: (-s['score'], s['tag']))
    for s in ordered:
        m = s['modules']
        lines.append(f"| {md_cell(s['tag'])} | {s['score']:.2f} | {m['基础']:.2f} | {m['编程']:.2f} | {m['工具']:.2f} | {m['文档']:.2f} | {len(s['hard_failures'])} |")
    if not valid:
        lines += ['', '没有可排名的完整锁分结果。']
    lines += ['', '## 用时', '', '| 模型 | 累计模型回答分钟 |', '|---|---:|']
    for s in sorted(valid, key=lambda s: (s['seconds'], s['tag'])):
        lines.append(f"| {md_cell(s['tag'])} | {s['seconds']/60:.2f} |")
    lines += ['', '不含加载、工具执行、隔离测试、人审或报告生成，不等同于tokens/s。', '', '## 无效或待复核', '']
    lines += [f"- {md_cell(s['tag'])}：{'；'.join(s['reasons'])}" for s in invalid] or ['无。']
    lines += ['', '## 解读边界', '', '一次主卷只能筛候选，不能推断长期稳定性或真实业务安全。']
    if len(ordered) > 1 and ordered[0]['score'] - ordered[1]['score'] <= 3:
        lines.append('前两名分差不超过3分，应视为接近候选并补测，不作显著优劣判断。')
    if any(s['hard_failures'] for s in summaries):
        lines.append('存在硬失败：不得用速度抵消，不能据此推荐自动执行或替换。')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    t = sub.add_parser('template')
    t.add_argument('--output', required=True)
    v = sub.add_parser('validate')
    v.add_argument('input')
    r = sub.add_parser('report')
    r.add_argument('inputs', nargs='+')
    r.add_argument('--output', required=True)
    r.add_argument('--allow-demo', action='store_true')
    args = parser.parse_args(argv)
    try:
        root = workspace_root(Path.cwd())
        if args.action == 'template':
            write_new(root, args.output, json.dumps(new_template(), ensure_ascii=False, indent=2) + '\n')
            print('已创建空白示例模板；不是已完成测评。')
        elif args.action == 'validate':
            summary = validate(read_json(root, args.input))
            print(json.dumps({'structure_valid': True, 'rankable': summary['rankable'], 'reasons': summary['reasons']}, ensure_ascii=False))
        else:
            # Validate output before reading any input; no scan or overwrite.
            file_path(root, args.output, must_exist=False)
            runs = [read_json(root, p) for p in args.inputs]
            write_new(root, args.output, report(runs, allow_demo=args.allow_demo))
            print('已生成离线对比报告。')
        return 0
    except (ValueError, OSError, TypeError, KeyError, UnicodeError) as exc:
        if isinstance(exc, (OSError, UnicodeError)):
            message = '无法读写文件；请检查相对路径、权限或已有输出。'
        else:
            message = str(exc) if isinstance(exc, ValueError) else '结果结构不符合契约。'
        print('错误：' + message)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
