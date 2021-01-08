#!/usr/bin/env python3
import platform
import sys

if platform.system() != "Linux":
    print(
        "FATAL: Zuul is supported only on Linux. Please read README.rst",
        file=sys.stderr)
    sys.exit(2)
