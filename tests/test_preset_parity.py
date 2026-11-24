"""Verify 1:1 parameter schema parity between StockShieldLowDdBot.cs and all .cbotset presets."""

from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "python"))

from generate_presets import extract_cs_parameter_names


def test_all_presets_match_cs_parameters_exactly():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cs_path = os.path.join(root, "cbot", "src", "StockShieldLowDdBot.cs")
    cs_params = extract_cs_parameter_names(cs_path)
    assert len(cs_params) >= 40

    preset_files = sorted(glob.glob(os.path.join(root, "cbot", "presets", "*.cbotset")))
    assert len(preset_files) == 4

    for pf in preset_files:
        with open(pf, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "Chart" in data and "Parameters" in data
        keys = set(data["Parameters"].keys())
        assert keys == cs_params, f"Mismatch in {os.path.basename(pf)}: extra={keys - cs_params}, missing={cs_params - keys}"
