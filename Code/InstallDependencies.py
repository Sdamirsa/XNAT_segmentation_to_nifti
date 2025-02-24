#!/usr/bin/env python3
"""
InstallDependencies.py

This script installs the necessary Python libraries for the XNAT-to-NIfTI pipeline.
It uses subprocess and sys to call pip install commands programmatically.

Usage:
    python InstallDependencies.py
"""

import sys
import subprocess

def install_packages():
    """
    Installs required Python packages for this pipeline.
    """
    packages = [
        "pydicom",
        "pynrrd",
        "nibabel",
        "openpyxl",  # for optional Excel handling in step 2.2
        "numpy",
        "pandas"     # optional, can be helpful for data manipulation
    ]
    for pkg in packages:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

if __name__ == "__main__":
    install_packages()