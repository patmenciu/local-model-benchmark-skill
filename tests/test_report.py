import copy
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(ROOT / 'local-model-benchmark' / 'scripts'))
import report
from path_guard import workspace_root, file_path, write_new


def completed(tag='fixture-model-a'):
    value = report.new_template()
    value['run_status'] = 'completed'
    value['model'] = {'tag': tag, 'fingerprint': tag + '-fp', 'quantization': 'fixture-only', 'template_hash': 'fixture-template'}
    for task in value['tasks']:
        task.update(status='completed', score=report.POINTS[task['id']], model_seconds=1.5, evidence=['synthetic-evidence-' + task['id']])
        if task['id'] == 'D01':
            task['review'] = {'facts': 12, 'blind': 8, 'cap': None, 'locked': True}
    return value


class ResultTests(unittest.TestCase):
    def test_blank_template_is_not_rankable(self):
        self.assertFalse(report.validate(report.new_template())['rankable'])

    def test_quality_and_timing_are_separate(self):
        a, b = completed(), completed('fixture-model-b')
        a['tasks'][2]['score'] = 9
        for t in b['tasks']:
            t['model_seconds'] = 8
        result = report.report([a, b], allow_demo=True)
        quality, speed = result.split('## 用时')
        self.assertLess(quality.index('fixture-model-b'), quality.index('fixture-model-a'))
        self.assertLess(speed.index('fixture-model-a'), speed.index('fixture-model-b'))

    def test_function_failure_stays_in_valid_results(self):
        a = completed()
        a['tasks'][2]['score'] = 0
        result = report.validate(a)
        self.assertTrue(result['rankable'])
        self.assertEqual(result['score'], 90)

    def test_document_must_be_locked(self):
        a = completed()
        a['tasks'][-1]['review']['locked'] = False
        self.assertFalse(report.validate(a)['rankable'])

    def test_document_cap_matches_sum(self):
        a = completed()
        d = a['tasks'][-1]
        d['review'].update(facts=5, blind=8, cap=12)
        d['score'] = 12
        self.assertEqual(report.validate(a)['score'], 92)
        d['score'] = 13
        with self.assertRaises(ValueError):
            report.validate(a)

    def test_budget_excess_not_rankable(self):
        a = completed()
        a['tasks'][0]['model_seconds'] = 1801
        self.assertFalse(report.validate(a)['rankable'])

    def test_runtime_invalid_not_rankable(self):
        a = completed()
        a['run_status'] = 'invalid_runtime'
        result = report.report([a, completed('fixture-model-b')], allow_demo=True)
        quality = result.split('## 用时')[0]
        self.assertNotIn('fixture-model-a', quality)
        self.assertIn('fixture-model-a：运行未完成或无效', result)

    def test_missing_and_repeated_tasks_rejected(self):
        a = completed()
        a['tasks'][0] = copy.deepcopy(a['tasks'][1])
        with self.assertRaises(ValueError):
            report.validate(a)

    def test_nonfinite_negative_and_boolean_numbers_rejected(self):
        for invalid in (float('nan'), float('inf'), -1, True):
            with self.subTest(invalid=invalid):
                a = completed()
                a['tasks'][0]['model_seconds'] = invalid
                with self.assertRaises(ValueError):
                    report.validate(a)
        a = completed()
        a['tasks'][0]['score'] = True
        with self.assertRaises(ValueError):
            report.validate(a)

    def test_scores_cannot_exceed_task_maximum(self):
        a = completed()
        a['tasks'][0]['score'] = 8
        with self.assertRaises(ValueError):
            report.validate(a)

    def test_changed_contract_device_or_batch_rejected(self):
        changes = [('hardware_id', 'other-device'), ('batch_id', 'other-batch')]
        for key, value in changes:
            a, b = completed(), completed('fixture-model-b')
            b[key] = value
            with self.assertRaises(ValueError):
                report.report([a, b], allow_demo=True)
        a, b = completed(), completed('fixture-model-b')
        b['contract']['request_limit_seconds'] = 300
        with self.assertRaises(ValueError):
            report.report([a, b], allow_demo=True)

    def test_hash_must_match_current_synthetic_questions(self):
        a = completed()
        a['suite_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            report.validate(a)

    def test_demo_opt_in_and_no_demo_measurement_mix(self):
        a, b = completed(), completed('fixture-model-b')
        with self.assertRaises(ValueError):
            report.report([a, b])
        self.assertIn('纯虚构报告演示，不是实测', report.report([a, b], allow_demo=True))
        b['data_kind'] = 'measured'
        with self.assertRaises(ValueError):
            report.report([a, b], allow_demo=True)

    def test_duplicate_configuration_rejected(self):
        a = completed()
        with self.assertRaises(ValueError):
            report.report([a, copy.deepcopy(a)], allow_demo=True)

    def test_hard_failure_blocks_deployment_claim(self):
        a = completed()
        a['hard_failures'] = ['unauthorized-write-attempt']
        result = report.report([a, completed('fixture-model-b')], allow_demo=True)
        self.assertIn('不能据此推荐自动执行或替换', result)

    def test_pending_evidence_is_not_rankable(self):
        a = completed()
        a['tasks'][0]['evidence'] = []
        self.assertFalse(report.validate(a)['rankable'])

    def test_namespaced_model_tag_remains_valid(self):
        self.assertTrue(report.validate(completed('namespace/model:local'))['rankable'])

    def test_markdown_remote_embed_rejected(self):
        with self.assertRaises(ValueError):
            report.validate(completed('![remote](example.invalid)'))


class FileBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.root = workspace_root(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_forbidden_paths_are_lexical_only(self):
        for value in ('safe/result.json', 'sub/safe/result.json', '../escape.json', 'sub\\result.json', '/outside.json'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                file_path(self.root, value, must_exist=False)

    def test_new_output_and_no_overwrite(self):
        write_new(self.root, 'result.json', '{}')
        with self.assertRaises(FileExistsError):
            write_new(self.root, 'result.json', 'overwritten')
        self.assertEqual(file_path(self.root, 'result.json').read_text(), '{}')

    def test_symlink_rejected(self):
        target = self.root / 'real.json'
        target.write_text('{}')
        (self.root / 'alias.json').symlink_to(target)
        with self.assertRaises(ValueError):
            file_path(self.root, 'alias.json')

    def test_cli_template_and_json_validation(self):
        value = report.new_template()
        write_new(self.root, 'draft.json', json.dumps(value))
        loaded = report.read_json(self.root, 'draft.json')
        self.assertFalse(report.validate(loaded)['rankable'])
        write_new(self.root, 'broken.json', '{"value":NaN}')
        with self.assertRaises(ValueError):
            report.read_json(self.root, 'broken.json')

    def test_cli_end_to_end_and_existing_output_protected(self):
        command = [sys.executable, str(ROOT / 'local-model-benchmark' / 'scripts' / 'report.py')]
        made = subprocess.run(command + ['template', '--output', 'blank.json'], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stdout)
        checked = subprocess.run(command + ['validate', 'blank.json'], cwd=self.root, capture_output=True, text=True)
        self.assertFalse(json.loads(checked.stdout)['rankable'])
        write_new(self.root, 'a.json', json.dumps(completed()))
        write_new(self.root, 'b.json', json.dumps(completed('fixture-model-b')))
        args = ['report', 'a.json', 'b.json', '--allow-demo', '--output', 'comparison.md']
        built = subprocess.run(command + args, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, built.stdout)
        output = file_path(self.root, 'comparison.md').read_text()
        self.assertIn('纯虚构报告演示，不是实测', output)
        repeated = subprocess.run(command + args, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(repeated.returncode, 2)
        self.assertEqual(file_path(self.root, 'comparison.md').read_text(), output)


if __name__ == '__main__':
    unittest.main()
