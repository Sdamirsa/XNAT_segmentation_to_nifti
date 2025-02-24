#!/usr/bin/env python3
"""
PickelViewer_for_DecodedSegment.py

This script reads a pickle file containing decoded segmentation data from XNAT,
prints its content in a readable format, and optionally decodes a single stacked-segmentation
DICOM file from XNAT, extracting per-frame info (segment number, image position, etc.),
mapping segment numbers to names, reading pixel data, and saving each segmentation object
as a pickle in a dedicated folder structure.

Author: YourName
Date: YYYY-MM-DD
"""

import os
import pickle
import sys
import pydicom

def show_pickle_content(pickle_file_path):
    """
    Reads a pickle file and prints its content in a readable format.

    Parameters
    ----------
    pickle_file_path : str
        Path to the pickle file to be read.
    """
    if not os.path.exists(pickle_file_path):
        raise FileNotFoundError(f"Pickle file not found: {pickle_file_path}")

    with open(pickle_file_path, "rb") as pkl_file:
        content = pickle.load(pkl_file)

    print("Pickle file content:")
    for key, value in content.items():
        if isinstance(value, (list, dict)):
            print(f"{key}:")
            for sub_key, sub_value in value.items() if isinstance(value, dict) else enumerate(value):
                print(f"  {sub_key}: {sub_value}")
        else:
            print(f"{key}: {value}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        pickle_file_path = input("Enter the path to the pickle file: ")
    elif len(sys.argv) > 2:
        print("Usage: python Code/PickelViewer_for_DecodedSegment.py <pickle_file_path>")
        sys.exit(1)
    else:
        pickle_file_path = sys.argv[1]

    
    show_pickle_content(pickle_file_path)