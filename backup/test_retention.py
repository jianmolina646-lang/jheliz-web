"""Offline tests: no real remote commands or production files."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('complete', Path(__file__).with_name('production-complete.py'))
backup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup)


class RetentionTests(unittest.TestCase):
    def test_independent_limits_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            names = [f'jheliz-complete-202608{i:02d}-010000.tar.gz.age' for i in range(1, 16)]
            weekly = [f'jheliz-complete-2026-W{i:02d}.tar.gz.age' for i in range(20, 26)]
            monthly = [f'jheliz-complete-2026{i:02d}.tar.gz.age' for i in range(1, 7)]
            (state/'inventory.json').write_text(json.dumps({'daily':names,'weekly':weekly,'monthly':monthly}))
            for name in names:
                (state/name).touch()
            calls = []
            def run(*args):
                calls.append(args)
                if 'mega-ls' in args:
                    return '\n'.join(names+weekly+monthly).encode()
                return b''
            with patch.object(backup,'STATE',state), patch.object(backup,'run',side_effect=run):
                backup.retention('r2:test/jheliztv.xyz/complete-v2',state/names[-1])
                result = json.loads((state/'inventory.json').read_text())
                for tier, limits in {'daily':(7,3),'weekly':(4,2),'monthly':(3,1)}.items():
                    self.assertEqual(len(result[tier]),limits[0])
                    self.assertEqual(len(result['_mega'][tier]),limits[1])
                self.assertEqual(len(list(state.glob('*.age'))),2)
                self.assertFalse(any('moveto' in call for call in calls))
                calls.clear()
                backup.retention('r2:test/jheliztv.xyz/complete-v2',state/names[-1])
                self.assertFalse(any('deletefile' in call or 'mega-rm' in call for call in calls))

    def test_invalid_inventory_stops_before_remote_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state/'inventory.json').write_text(json.dumps({'daily':['../../other-project']}))
            with patch.object(backup,'STATE',state), patch.object(backup,'run') as run:
                with self.assertRaises(RuntimeError):
                    backup.retention('r2:test',state/'jheliz-complete-20260907-010000.tar.gz.age')
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
