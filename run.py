#!/usr/bin/env python3
"""Obsidibear entry point — run from within the repo directory."""
import os
import sys

# Add parent directory so 'obsidibear' package is discoverable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from obsidibear.cli import main

main()
