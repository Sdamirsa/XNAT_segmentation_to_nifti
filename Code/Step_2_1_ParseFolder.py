#!/usr/bin/env python3
"""
Step_2_1_ParseFolder.py

Reads the SCANS and ASSESSORS subdirectories for a given study folder.
Extracts metadata from DICOM and XML to create JSON files:
    - StudySeries_info.json
    - Segmentations_info.json

Saves these JSON files in an output directory specified by the user,
under a subfolder matching the study folder name. For example:
    python Step_2_1_ParseFolder.py /path/to/2072 /path/to/output
    => Will create /path/to/output/2072/StudySeries_info.json
       and   /path/to/output/2072/Segmentations_info.json

Author: SAA Safavi-Naini
Date: 2025-02-05
"""

import os
import sys
import json
import random
import pydicom
import xml.etree.ElementTree as ET

def parse_scans_info(study_path, output_dir, output_json="StudySeries_info.json"):
    """
    Parse the SCANS folder to extract basic DICOM info for each series.
    Writes results to a JSON file in output_dir.

    Parameters
    ----------
    study_path : str
        Path to the main study folder (e.g., '.../2072').
        This folder must contain a subfolder named 'SCANS'.
    output_dir : str
        Path to the directory where the output JSON should be stored.
        The file is named output_json inside this directory.
    output_json : str, optional
        Filename (not path) for saving the SCANS metadata as JSON.
        Defaults to 'StudySeries_info.json'.

    Returns
    -------
    dict
        A dictionary mapping each SCANS subfolder to a dictionary with extracted fields:
            {
                "series_folder_path": str,
                "series_number": str or None,
                "series_uid": str or None,
                "series_description": str or None,
                "class_uid": str or None,
                "scan_errors": str or None
            }
        This dictionary is also written to <output_dir>/<output_json>.
    """
    scans_dir = os.path.join(study_path, "SCANS")
    if not os.path.exists(scans_dir):
        raise FileNotFoundError(f"SCANS directory not found in {study_path}")

    all_scans_info = {}
    # List each subfolder in SCANS
    for series_folder_name in os.listdir(scans_dir):
        series_folder_path = os.path.join(scans_dir, series_folder_name)
        dicom_folder_path = os.path.join(series_folder_path, "DICOM")

        if not os.path.isdir(dicom_folder_path):
            continue

        # Attempt to read two random DICOM files (or the first two if not enough)
        dcm_files = [f for f in os.listdir(dicom_folder_path) if f.lower().endswith(".dcm")]
        if len(dcm_files) == 0:
            # No DICOM files
            all_scans_info[series_folder_name] = {
                "series_folder_path": dicom_folder_path,
                "series_number": None,
                "series_uid": None,
                "series_description": None,
                "class_uid": None,
                "scan_errors": "No DICOM files found"
            }
            continue

        if len(dcm_files) > 2:
            selected_files = random.sample(dcm_files, 2)
        else:
            selected_files = dcm_files

        info_list = []
        error_message = None

        for dcm_file in selected_files:
            dcm_path = os.path.join(dicom_folder_path, dcm_file)
            try:
                ds = pydicom.dcmread(dcm_path, stop_before_pixels=True, force=True)
                series_number = getattr(ds, "SeriesNumber", None)  # (0020,0011)
                # Per instructions, check for (0020,0003) then fallback to (0020,000E).
                series_uid = ds.get((0x0020, 0x0003), None)
                if series_uid is None:
                    series_uid = getattr(ds, "SeriesInstanceUID", None)

                series_description = getattr(ds, "SeriesDescription", None)  # (0008,103E)
                class_uid = getattr(ds, "SOPClassUID", None)  # (0008,0016)

                info_list.append({
                    "series_number": str(series_number) if series_number else None,
                    "series_uid": str(series_uid),
                    "series_description": str(series_description),
                    "class_uid": str(class_uid)
                })
            except Exception as e:
                error_message = f"Error reading {dcm_path}: {e}"
                info_list.append({
                    "series_number": None,
                    "series_uid": None,
                    "series_description": None,
                    "class_uid": None
                })

        # Check for inconsistency if we have 2 items
        if len(info_list) == 2:
            fields_to_compare = ["series_number", "series_uid", "series_description", "class_uid"]
            mismatch = any(
                info_list[0][fld] != info_list[1][fld] for fld in fields_to_compare
            )
            if mismatch:
                error_message = f"Inconsistent metadata in {series_folder_name}"

        chosen_info = info_list[0] if len(info_list) > 0 else {}

        all_scans_info[series_folder_name] = {
            "series_folder_path": dicom_folder_path,
            "series_number": chosen_info.get("series_number", None),
            "series_uid": chosen_info.get("series_uid", None),
            "series_description": chosen_info.get("series_description", None),
            "class_uid": chosen_info.get("class_uid", None),
            "scan_errors": error_message
        }

    # Save as JSON in output_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = os.path.join(output_dir, output_json)
    with open(output_path, "w") as f:
        json.dump(all_scans_info, f, indent=4)
    return all_scans_info


def parse_assessors_info(study_path, output_dir, output_json="Segmentations_info.json"):
    """
    Parse the ASSESSORS folder to extract XML-based segmentor info and DICOM-based segmentation info.
    Writes results to a JSON file in output_dir.

    Parameters
    ----------
    study_path : str
        Path to the main study folder (e.g., '.../2072').
        This folder must contain a subfolder named 'ASSESSORS'.
    output_dir : str
        Path to the directory where the output JSON should be stored.
        The file is named output_json inside this directory.
    output_json : str, optional
        Filename (not path) for saving the ASSESSORS metadata as JSON.
        Defaults to 'Segmentations_info.json'.

    Returns
    -------
    dict
        A dictionary mapping each ASSESSORS subfolder to the extracted fields:
            {
                "assessor_folder_path": str,
                "segmentor_name": str,
                "created_time": str,
                "exported_name": str,  # (0008,103E)
                "ref_class_uid": str,  # comma-separated if more than one
                "ref_series_uid": str or None,
                "errors": str or None
            }
        This dictionary is also written to <output_dir>/<output_json>.
    """
    assessors_dir = os.path.join(study_path, "ASSESSORS")
    if not os.path.exists(assessors_dir):
        raise FileNotFoundError(f"ASSESSORS directory not found in {study_path}")

    all_assessors_info = {}
    for assessor_folder_name in os.listdir(assessors_dir):
        assessor_folder_path = os.path.join(assessors_dir, assessor_folder_name)
        seg_folder_path = os.path.join(assessor_folder_path, "SEG")

        if not os.path.isdir(seg_folder_path):
            continue

        # Expect exactly one .dcm for the segmentation
        dcm_files = [f for f in os.listdir(seg_folder_path) if f.lower().endswith(".dcm")]
        xml_files = [f for f in os.listdir(seg_folder_path) if f.lower().endswith(".xml")]

        segmentor_name = None
        created_time = None
        exported_name = None
        ref_class_uid_set = set()
        ref_series_uid = None
        errors = None

        # Parse XML for 'createdBy' & 'createdTime' in <cat:entry ...>
        for xml_file in xml_files:
            xml_path = os.path.join(seg_folder_path, xml_file)
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
                entries = root.findall(".//{*}entry")
                for entry_elem in entries:
                    if entry_elem is not None:
                        possible_dcm_id = entry_elem.attrib.get("ID", "")
                        if possible_dcm_id in dcm_files:
                            segmentor_name = entry_elem.attrib.get("createdBy", None)
                            created_time = entry_elem.attrib.get("createdTime", None)
                            break
            except Exception as e:
                if errors:
                    errors += f" | Error parsing XML {xml_path}: {str(e)}"
                else:
                    errors = f"Error parsing XML {xml_path}: {str(e)}"

        # Parse the DICOM for (0008,103E) description, ref_class_uid, ref_series_uid
        for dcm_file in dcm_files:
            dcm_path = os.path.join(seg_folder_path, dcm_file)
            try:
                ds = pydicom.dcmread(dcm_path, stop_before_pixels=True, force=True)

                # (0008,103E)
                desc_elem = ds.get((0x0008, 0x103E))
                if desc_elem is not None:
                    exported_name = desc_elem.value
                else:
                    exported_name = "Unknown"

                # Collect SOP Class UIDs from ReferencedSeriesSequence->ReferencedInstanceSequence
                if hasattr(ds, "ReferencedSeriesSequence"):
                    for series_item in ds.ReferencedSeriesSequence:
                        if hasattr(series_item, "ReferencedInstanceSequence"):
                            for ref_inst_item in series_item.ReferencedInstanceSequence:
                                sop_class_uid_elem = ref_inst_item.get((0x0008, 0x1150), None)
                                if sop_class_uid_elem is not None:
                                    sop_class_uid_val = sop_class_uid_elem.value
                                    ref_class_uid_set.add(sop_class_uid_val)

                        # Series Instance UID
                        if hasattr(series_item, "SeriesInstanceUID"):
                            ref_series_uid = series_item.SeriesInstanceUID

            except Exception as e:
                if errors:
                    errors += f" | Error parsing DICOM {dcm_path}: {str(e)}"
                else:
                    errors = f"Error parsing DICOM {dcm_path}: {str(e)}"

        # Convert the set of unique UIDs to a comma-separated string
        if ref_class_uid_set:
            ref_class_uid_str = ",".join(sorted(ref_class_uid_set))
        else:
            ref_class_uid_str = None

        all_assessors_info[assessor_folder_name] = {
            "assessor_folder_path": seg_folder_path,
            "segmentor_name": segmentor_name,
            "created_time": created_time,
            "exported_name": str(exported_name) if exported_name else None,
            "ref_class_uid": ref_class_uid_str,
            "ref_series_uid": str(ref_series_uid) if ref_series_uid else None,
            "errors": errors
        }

    # Save as JSON in output_dir
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = os.path.join(output_dir, output_json)
    with open(output_path, "w") as f:
        json.dump(all_assessors_info, f, indent=4)
    return all_assessors_info


def main(study_path, output_base):
    """
    Main function to parse a single study folder for SCANS and ASSESSORS info,
    and write JSON files to an output directory.

    Parameters
    ----------
    study_path : str
        Path to the main study folder (e.g., '.../2072').
    output_base : str
        Directory where we will create a subfolder named after the study
        and save the JSON outputs.

    Returns
    -------
    None
    """
    # Get the final part of study_path (e.g., '2072')
    study_name = os.path.basename(os.path.normpath(study_path))
    study_output_folder = os.path.join(output_base, study_name)

    parse_scans_info(study_path, output_dir=study_output_folder, output_json="StudySeries_info.json")
    parse_assessors_info(study_path, output_dir=study_output_folder, output_json="Segmentations_info.json")


if __name__ == "__main__":
    # Example usage:
    #   python Step_2_1_ParseFolder.py <study_path> <output_base>
    #
    # If the user only passes <study_path>, fallback to a default output folder.
    # If nothing is passed, prompt for both.

    if len(sys.argv) == 1:
        study_path_arg = input("Enter the study folder path: ")
        output_base_arg = input("Enter the base output folder: ")
    elif len(sys.argv) == 2:
        study_path_arg = sys.argv[1]
        # Default to a subfolder named "output" in the same directory as the study
        study_parent = os.path.dirname(os.path.normpath(study_path_arg))
        output_base_arg = os.path.join(study_parent, "output")
    elif len(sys.argv) == 3:
        study_path_arg = sys.argv[1]
        output_base_arg = sys.argv[2]
    else:
        print("Usage: python Step_2_1_ParseFolder.py <study_path> [output_base]")
        sys.exit(1)

    if not os.path.exists(study_path_arg):
        print(f"Study path not found: {study_path_arg}")
        sys.exit(1)

    # Ensure the output base folder exists
    if not os.path.exists(output_base_arg):
        os.makedirs(output_base_arg, exist_ok=True)

    main(study_path_arg, output_base_arg)