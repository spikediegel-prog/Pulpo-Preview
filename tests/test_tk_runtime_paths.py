import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pulpo.tuning_app import _prepare_tk_libraries


class TkRuntimePathTests(unittest.TestCase):
    def test_local_runtime_selected_before_tk_without_overwriting_explicit_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tcl = root / "tcl" / "tcl8.6"
            tk = root / "tcl" / "tk8.6"
            tcl.mkdir(parents=True)
            tk.mkdir(parents=True)
            (tcl / "init.tcl").write_text("fixture")
            (tk / "tk.tcl").write_text("fixture")
            with patch("pulpo.tuning_app.sys.prefix", str(root)), patch.dict(os.environ, {}, clear=True):
                _prepare_tk_libraries()
                self.assertEqual(tcl, Path(os.environ["TCL_LIBRARY"]).resolve())
                self.assertEqual(tk, Path(os.environ["TK_LIBRARY"]).resolve())
                os.environ["TCL_LIBRARY"] = "explicit-tcl"
                os.environ["TK_LIBRARY"] = "explicit-tk"
                _prepare_tk_libraries()
                self.assertEqual("explicit-tcl", os.environ["TCL_LIBRARY"])
                self.assertEqual("explicit-tk", os.environ["TK_LIBRARY"])
