#!/usr/bin/env python3
"""
Step_2_2_SelectSegmentations.py

Allows user interaction or Excel-based filtering of which segmentations to use.
- Reads an existing Segmentations_info.json (default in the same directory as the study).
- If an Excel file is provided, we parse a column with case numbers and a column "Segmentations".
  We look for a row matching the given case_number. The "Segmentations" cell can contain:
       - comma-separated or semicolon-separated segmentation names, (you can have it inside bracket or without brackets)
       - or the keyword 'all'.
- If manual is True, the user can see a list of available segmentations and select from them.
       - If the user types "all", then all segmentations are selected.

We match the user's requested segmentation names against:
   - The folder name (e.g. SEG_20241021_181708_943_S2)
   - The exported_name (e.g. "fff_elhamgp_PAS")

Any user-provided name not found is saved in error_provided_name_not_valid_in_SEGs.

Finally, we save a JSON with:
    {
      "selected_segmentations": {
         "SEG_XXXXXX": {...},  # same structure as in Segmentations_info.json
         ...
      },
      "error_provided_name_not_valid_in_SEGs": [...]
    }

Usage (interactive):
    python Step_2_2_SelectSegmentations.py
Or programmatically from another script.

Author: SAA Safavi-Naini
Date: 2025-02-05
"""

import os
import json

try:
    import openpyxl
except ImportError:
    openpyxl = None  # in case user didn't install; Step_2_2 is optional.

def load_segmentations_info(seg_info_path):
    """
    Load the existing Segmentations_info.json file.

    Parameters
    ----------
    seg_info_path : str
        Path to Segmentations_info.json

    Returns
    -------
    dict
        The parsed JSON dictionary of all segmentations info.
    """
    if not os.path.exists(seg_info_path):
        raise FileNotFoundError(f"Segmentations_info.json not found at: {seg_info_path}")
    with open(seg_info_path, "r") as f:
        data = json.load(f)
    return data

def get_selection_from_excel(excel_file, case_number):
    """
    Parse an Excel file (assuming columns "CaseNumber" and "Segmentations") to find
    the row matching `case_number`. Return the list of requested segmentations or an empty list.

    Parameters
    ----------
    excel_file : str
        Path to an Excel file.
    case_number : str or int
        The study ID or case number to match in the "CaseNumber" column.

    Returns
    -------
    list
        List of requested segmentation names. Could contain 'all' if user typed that in Excel.
    """
    selections = []
    wb = openpyxl.load_workbook(excel_file)
    ws = wb.active

    # Find columns: "CaseNumber" and "Segmentations"
    case_col = None
    seg_col = None

    for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if idx == 1:
            # header row
            for col_idx, val in enumerate(row):
                if str(val).lower() == "casenumber":
                    case_col = col_idx
                if str(val).lower() == "segmentations":
                    seg_col = col_idx
            continue

        if case_col is not None and seg_col is not None:
            row_case = row[case_col]
            if str(row_case) == str(case_number):
                row_segs = row[seg_col]
                if row_segs is not None:
                    if isinstance(row_segs, str):
                        # Check if the string is a list-like format
                        if row_segs.startswith("[") and row_segs.endswith("]"):
                            row_segs = row_segs[1:-1]  # Remove the brackets
                        splitted = [s.strip() for s in row_segs.replace(";", ",").split(",")]
                        selections.extend(splitted)
                    else:
                    # might be a single value
                        selections.append(str(row_segs))
                break

    return selections

def get_selection_manually(available_folders, available_exported_names):
    """
    Interactive approach to select which segmentations are valid.
    If user types "all", we return ["all"].

    Parameters
    ----------
    available_folders : list
        List of segmentation folder names (e.g. ["SEG_20241021_181708_943_S2", ...]).
    available_exported_names : list
        List of exported names (e.g. ["fff_elhamgp_PAS", ...]) in the same order or set.

    Returns
    -------
    list
        List of user-typed segmentation names.
        Could contain 'all'.
    """
    print("\nAvailable segmentation FOLDER names:")
    for folder in available_folders:
        print("  ", folder)
    print("\nAvailable segmentation EXPORTED names:")
    for ename in available_exported_names:
        print("  ", ename)

    print("\nType the segmentation(s) to select (comma separated), or 'all' to select everything.")
    segs_str = input(">> ")
    # user can type "all" or multiple
    if segs_str.strip().lower() == "all":
        return ["all"]
    else:
        return [s.strip() for s in segs_str.split(",") if s.strip()]

def match_segmentations(user_requests, seg_info):
    """
    Match user-requested segmentation names to the available segmentations in seg_info.
    We consider:
      - Keys (folder names) in seg_info
      - "exported_name" from seg_info

    If "all" is in user_requests, we return all segmentations.
    Return:
      selected_dict: the sub-dict of seg_info that matched
      not_found_list: user-requested strings that didn't match anything

    Parameters
    ----------
    user_requests : list
        List of strings typed by the user or from Excel (e.g. ["SEG_2024...", "fff_elhamgp_PAS", ...]).
        Could contain "all".
    seg_info : dict
        Dictionary from Segmentations_info.json, structured as:
            {
               "SEG_20241021_181708_943_S2": {
                    "assessor_folder_path": ...,
                    "exported_name": ...,
                    ...
               },
               ...
            }

    Returns
    -------
    (dict, list)
        selected_dict:
          A subset of seg_info with only the matched keys.
        not_found_list:
          The user strings that did not match any folder or exported_name.
    """

    if "all" in [r.lower() for r in user_requests]:
        # If user asked for all, no need to search
        return seg_info.copy(), []

    matched = {}
    not_found = []

    # Pre-build a map from folder-key to key, and exported_name to key
    folder_map = {}
    exported_map = {}
    for folder_key, info_dict in seg_info.items():
        # folder_key is e.g. "SEG_20241021_181708_943_S2"
        folder_map[folder_key.lower()] = folder_key

        exported_name = info_dict.get("exported_name", "")
        if exported_name:
            exported_map[exported_name.lower()] = folder_key

    for requested_name in user_requests:
        lower_req = requested_name.lower()
        found_key = None

        # Check folder map
        if lower_req in folder_map:
            found_key = folder_map[lower_req]
        # Check exported map only if not found
        elif lower_req in exported_map:
            found_key = exported_map[lower_req]

        if found_key is not None:
            matched[found_key] = seg_info[found_key]
        else:
            not_found.append(requested_name)

    return matched, not_found

def save_selected_segmentations(output_path, selected_dict, not_found_list):
    """
    Save the final JSON with two top-level keys:
      "selected_segmentations"
      "error_provided_name_not_valid_in_SEGs"

    Example structure:
      {
        "selected_segmentations": {
          "SEG_20241021_181708_943_S2": {...},
          ...
        },
        "error_provided_name_not_valid_in_SEGs": ["someName", "otherName"]
      }

    Parameters
    ----------
    output_path : str
        Where to save the JSON (e.g. "SelectedSegmentations_info.json")
    selected_dict : dict
        Subset of the original Segmentations_info
    not_found_list : list
        List of user strings that were not matched
    """
    final_obj = {
        "selected_segmentations": selected_dict,
        "error_provided_name_not_valid_in_SEGs": not_found_list
    }
    with open(output_path, "w") as fp:
        json.dump(final_obj, fp, indent=4)

def main():
    """
    Main usage example and flow.

    1) Prompt user (or parse sys.argv) for:
       - segmentations_info_path (with default guess)
       - manual? (y/n)
       - or excel_file + case_number?
    2) Load segmentations_info
    3) Gather user selection
    4) Match them
    5) Save SelectedSegmentations_info.json
    """
    import sys

    # Attempt to gather from command line
    # e.g., python Step_2_2_SelectSegmentations.py "/path/to/Segmentations_info.json" --excel "/path/to/excel.xlsx" --case "2072"
    # or     python Step_2_2_SelectSegmentations.py "/path/to/Segmentations_info.json" --manual
    segmentations_info_path = None
    excel_file = None
    case_number = None
    use_manual = False

    if len(sys.argv) == 1:
        # no args => prompt
        default_path = os.path.join(os.getcwd(), "Segmentations_info.json")
        print(f"Enter path to Segmentations_info.json (default: {default_path}):")
        seg_path_in = input(">> ").strip()
        segmentations_info_path = seg_path_in if seg_path_in else default_path

        if not os.path.exists(segmentations_info_path):
            print("**ERROR**: Segmentations_info.json not found. Exiting.")
            return

        print("Manual selection or Excel-based? Type 'manual' or 'excel':")
        sel_mode = input(">> ").strip().lower()
        if sel_mode == "manual":
            use_manual = True
        elif sel_mode == "excel" and openpyxl:
            print("Enter path to Excel file:")
            excel_file = input(">> ").strip()
            if not os.path.exists(excel_file):
                print("**ERROR**: Excel file not found. Exiting.")
                return
            print("Enter case number to search in Excel:")
            case_in = input(">> ").strip()
            case_number = case_in
        else:
            print("Mode not recognized or openpyxl not installed. Exiting.")
            return
    else:
        # parse arguments
        # minimal approach: 1st arg = seg_info_path
        segmentations_info_path = sys.argv[1]
        if not os.path.exists(segmentations_info_path):
            print(f"**ERROR**: Segmentations_info.json not found at {segmentations_info_path}. Exiting.")
            return

        # We look for optional flags: --manual or --excel "xxx" --case "xxx"
        # Just a quick approach:
        i = 2
        while i < len(sys.argv):
            arg = sys.argv[i].lower()
            if arg == "--manual":
                use_manual = True
            elif arg == "--excel" and openpyxl:
                i += 1
                excel_file = sys.argv[i]
            elif arg == "--case":
                i += 1
                case_number = sys.argv[i]
            i += 1

    # Now load the JSON
    try:
        seg_info = load_segmentations_info(segmentations_info_path)
    except FileNotFoundError as e:
        print(str(e))
        return

    # Build the list of user requests
    user_requests = []

    if excel_file and case_number and not use_manual:
        # gather from Excel
        user_requests = get_selection_from_excel(excel_file, case_number)
        if not user_requests:
            print(f"[INFO] No matching segmentations found in Excel for case {case_number}. No selection made.")
            user_requests = []
    elif use_manual:
        # gather from manual
        available_folders = list(seg_info.keys())  # folder names
        available_exported_names = []
        for k, v in seg_info.items():
            ename = v.get("exported_name", "")
            available_exported_names.append(ename)
        user_requests = get_selection_manually(available_folders, available_exported_names)

    # If user_requests is empty, we do nothing. But let's allow user to type "all" or manually
    # handle the scenario of user leaving cell empty in Excel or no manual choice
    if not user_requests:
        print("[INFO] No segmentations were requested. Exiting with no selection.")
        return

    # Match them
    selected_dict, not_found_list = match_segmentations(user_requests, seg_info)

    # If user typed "all", that would have returned everything
    # If user typed something partial, we have partial matches
    # not_found_list has any that didn't match

    # Save final result to "SelectedSegmentations_info.json" in the same folder as Segmentations_info.json
    out_folder = os.path.dirname(os.path.abspath(segmentations_info_path))
    out_path = os.path.join(out_folder, "SelectedSegmentations_info.json")

    save_selected_segmentations(out_path, selected_dict, not_found_list)

    print(f"[INFO] Saved selection to {out_path}")
    print("Selected segmentations:")
    for k in selected_dict.keys():
        print("  ", k)
    if not_found_list:
        print("Unmatched requests:", not_found_list)

if __name__ == "__main__":
    main()