#!/usr/bin/env python3
"""Execute the synthetic protocol script for the current Rust test."""

import runpy

runpy.run_path("core.py", run_name="__main__")
