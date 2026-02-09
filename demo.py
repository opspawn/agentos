#!/usr/bin/env python3
"""AgentOS Demo Runner — standalone entry point.

Usage:
    python demo.py              # Default mode with realistic timing
    python demo.py --fast       # Fast mode (skip delays)
    python demo.py --budget 10  # Custom budget
"""

import os
import sys

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from demo.cli import main

if __name__ == "__main__":
    main()
