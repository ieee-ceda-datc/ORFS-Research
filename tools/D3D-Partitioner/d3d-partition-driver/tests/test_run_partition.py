from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "run_partition.py"
SPEC = importlib.util.spec_from_file_location("run_partition", MODULE_PATH)
RUN_PARTITION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN_PARTITION)


class D3DPartitionerSelectionTest(unittest.TestCase):
    def test_release_defaults_select_cpu_d3d(self) -> None:
        params = json.loads(RUN_PARTITION.DEFAULTS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(params["partitioner"], "d3d")
        self.assertEqual(params["gpu"], 0)
        self.assertNotIn("lef_input", params)
        self.assertNotIn("differentiable_partitioner_config_root", params)

    def test_accepts_d3d_aliases(self) -> None:
        for name in RUN_PARTITION.D3D_PARTITIONER_NAMES:
            with self.subTest(name=name):
                RUN_PARTITION.validate_d3d_partitioner({"partitioner": name})

    def test_rejects_non_d3d_partitioners(self) -> None:
        for name in (
            None,
            "",
            "hmetis",
            "tritonpart",
            "bin-based-tritonpart",
            "specpart",
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    RUN_PARTITION.validate_d3d_partitioner(
                        {"partitioner": name}
                    )


class D2DBinConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.params = json.loads(
            RUN_PARTITION.DEFAULTS_FILE.read_text(encoding="utf-8")
        )

    def test_applies_all_four_design_specific_bin_values(self) -> None:
        config = {
            "d2d": {
                "num_bins_x": 512,
                "num_bins_y": 512,
                "global_place_stages": [
                    {"num_bins_x": 512, "num_bins_y": 512}
                ],
            }
        }

        RUN_PARTITION.apply_d2d_bin_config(self.params, config)

        self.assertEqual(self.params["num_bins_x"], 512)
        self.assertEqual(self.params["num_bins_y"], 512)
        self.assertEqual(
            self.params["global_place_stages"][0]["num_bins_x"], 512
        )
        self.assertEqual(
            self.params["global_place_stages"][0]["num_bins_y"], 512
        )
        self.assertEqual(self.params["global_place_stages"][0]["iteration"], 20)

    def test_config_without_d2d_keeps_shared_defaults(self) -> None:
        expected = copy.deepcopy(self.params)
        RUN_PARTITION.apply_d2d_bin_config(
            self.params, {"design": {"name": "gcd"}}
        )
        self.assertEqual(self.params, expected)

    def test_rejects_unsynchronized_bin_values(self) -> None:
        config = {
            "d2d": {
                "num_bins_x": 512,
                "num_bins_y": 512,
                "global_place_stages": [
                    {"num_bins_x": 256, "num_bins_y": 512}
                ],
            }
        }
        with self.assertRaisesRegex(ValueError, "must be identical"):
            RUN_PARTITION.apply_d2d_bin_config(self.params, config)


if __name__ == "__main__":
    unittest.main()
