import contextlib
import io
import json
import unittest
from unittest.mock import patch

from scripts.security import probe_container_components as probe


class ContainerComponentProbeTests(unittest.TestCase):
    def test_privileged_or_incomplete_runtime_denied_before_command_execution(self):
        for uid, status in [(0, 'CapEff:\t0000000000000000\nNoNewPrivs:\t1'),
                            (1000, 'CapEff:\t0000000000000001\nNoNewPrivs:\t1'),
                            (1000, 'CapEff:\t0000000000000000\nNoNewPrivs:\t0'),
                            (1000, '')]:
            with self.subTest(uid=uid, status=status), patch.object(probe.os, 'geteuid', return_value=uid, create=True), \
                 patch.object(probe.Path, 'read_text', return_value=status), patch.object(probe, 'command') as command:
                with self.assertRaises(RuntimeError):
                    probe.main()
                command.assert_not_called()

    def test_inventory_is_not_an_advisory_waiver_or_environment_export(self):
        with patch.object(probe.os, 'geteuid', return_value=1000, create=True), \
             patch.object(probe.Path, 'read_text', return_value='CapEff:\t0000000000000000\nNoNewPrivs:\t1'), \
             patch.object(probe.Path, 'exists', return_value=False), \
             patch.object(probe.shutil, 'which', return_value=None), \
             patch.object(probe, 'command', return_value={'exit_code':0,'stdout':'','stderr':''}) as command, \
             patch.dict(probe.os.environ, {'PRIVATE_PROBE_SENTINEL':'do-not-export'}):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                probe.main()
            report=json.loads(output.getvalue())
            self.assertIn('no advisory waived',report['claim'])
            self.assertNotIn('do-not-export',output.getvalue())
            self.assertEqual({'exit_code':4,'stderr':'perl absent'},report['perl_modules']['Pod::Text'])
            self.assertTrue(all(call.args[0][0]=='dpkg-query' for call in command.call_args_list))


if __name__=='__main__':
    unittest.main()
