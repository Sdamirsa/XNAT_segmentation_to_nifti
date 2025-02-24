#!/usr/bin/env python3
"""
Step_2_3_DecodeSegmentation.py

Reads a JSON file containing selected segmentations (e.g. "SelectedSegmentations_info.json"),
iterates over each segmentation, locates the single .dcm inside its assessor folder, and
decodes the multi-frame DICOM to produce:

    1) A .pkl file (including 2D pixel_data for each frame).
    2) A .json file with the same metadata but without image data (smaller file size).

After generating those artifacts, we add the following fields to each segmentation in
the loaded JSON:
    - pkl_file
    - json_file
    - num_frames
    - segment_name_count (count of distinct segment_name values in frames)
    - ref_series_uid (the actual value read from the DICOM)

We then save this updated info to "PreparedSegmentations_info.json" in the same directory.

Author: SAA Safavi-Naini
Date: 2025-02-06
"""

import os
import sys
import json
import pickle
import pydicom
import numpy as np
from collections import Counter

def sanitize_for_json(obj):
    """
    Recursively convert any pydicom DataElement or other non-serializable objects
    into plain Python data structures (strings, lists, dicts, etc.).
    """
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, pydicom.dataelem.DataElement):
        return str(obj.value)
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(x) for x in obj]
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)


def decode_segmentation_dcm(seg_dcm_path):
    """
    Decode a single segmentation .dcm file (multi-frame SEG),
    returning a dictionary with fields:
        "segmentation_name"
        "segmentation_type"
        "ref_series_uid"
        "ref_sop_class_uid"
        "pixel_spacing"
        "slice_thickness"
        "spacing_between_slices"
        "image_orientation"
        "rows"
        "columns"
        "num_frames"
        "frames": [ {frame_index, segment_number, segment_name, segment_color,
                     image_position_patient, ref_sop_uid, pixel_data}, ... ]
    """
    if not os.path.exists(seg_dcm_path):
        raise FileNotFoundError(f"Seg DICOM not found: {seg_dcm_path}")

    ds = pydicom.dcmread(seg_dcm_path, force=True)

    # Basic info
    segmentation_name = getattr(ds, "SeriesDescription", "Unnamed_Segmentation")  # (0008,103E)
    seg_type_elem = ds.get((0x0062, 0x0001))
    if seg_type_elem:
        segmentation_type = str(seg_type_elem.value)
    else:
        segmentation_type = "UNKNOWN"

    # Referenced Series UID
    ref_series_uid = None
    if hasattr(ds, "ReferencedSeriesSequence") and len(ds.ReferencedSeriesSequence) > 0:
        ref_series_uid = getattr(ds.ReferencedSeriesSequence[0], "SeriesInstanceUID", None)

    # Top-level Referenced SOP Class UID
    ref_sop_class_uid_elem = ds.get((0x0008, 0x1150))
    if ref_sop_class_uid_elem:
        ref_sop_class_uid = ref_sop_class_uid_elem.value
    else:
        ref_sop_class_uid = None

    rows = getattr(ds, "Rows", None)
    columns = getattr(ds, "Columns", None)

    # Geometry from SharedFunctionalGroupsSequence
    pixel_spacing = None
    slice_thickness = None
    spacing_between_slices = None
    image_orientation = None

    if hasattr(ds, "SharedFunctionalGroupsSequence"):
        if len(ds.SharedFunctionalGroupsSequence) > 0:
            shared_item = ds.SharedFunctionalGroupsSequence[0]
            if hasattr(shared_item, "PixelMeasuresSequence") and len(shared_item.PixelMeasuresSequence) > 0:
                pm = shared_item.PixelMeasuresSequence[0]
                slice_thickness = getattr(pm, "SliceThickness", None)
                spacing_between_slices = getattr(pm, "SpacingBetweenSlices", None)
                ps = getattr(pm, "PixelSpacing", None)
                if ps:
                    pixel_spacing = [float(x) for x in ps]

            if hasattr(shared_item, "PlaneOrientationSequence") and len(shared_item.PlaneOrientationSequence) > 0:
                po = shared_item.PlaneOrientationSequence[0]
                iop = getattr(po, "ImageOrientationPatient", None)
                if iop:
                    image_orientation = [float(x) for x in iop]

    # Segment map
    segment_map = {}
    if hasattr(ds, "SegmentSequence"):
        for seg_item in ds.SegmentSequence:
            seg_num = getattr(seg_item, "SegmentNumber", None)
            seg_label = getattr(seg_item, "SegmentLabel", None)
            seg_color = getattr(seg_item, "RecommendedDisplayCIELabValue", None)
            if seg_num:
                if seg_color is not None and hasattr(seg_color, "__iter__"):
                    seg_color = list(seg_color)
                segment_map[seg_num] = {
                    "name": seg_label if seg_label else f"Label_{seg_num}",
                    "color": seg_color
                }

    # Build frames array
    frames = []
    pixel_array_3d = ds.pixel_array  # shape => (num_frames, rows, cols)
    num_frames = getattr(ds, "NumberOfFrames", 0)

    if hasattr(ds, "PerFrameFunctionalGroupsSequence") and len(ds.PerFrameFunctionalGroupsSequence) == num_frames:
        for frame_index in range(num_frames):
            frame = ds.PerFrameFunctionalGroupsSequence[frame_index]
            # SegmentIdentificationSequence
            segment_number = None
            if hasattr(frame, "SegmentIdentificationSequence") and len(frame.SegmentIdentificationSequence) > 0:
                seg_id_seq_item = frame.SegmentIdentificationSequence[0]
                segment_number = getattr(seg_id_seq_item, "ReferencedSegmentNumber", None)

            # seg_name, seg_color from segment_map
            seg_name = None
            seg_color = None
            if segment_number and segment_number in segment_map:
                seg_name = segment_map[segment_number]["name"]
                seg_color = segment_map[segment_number]["color"]

            # ref_sop_uid -> DerivationImageSequence => SourceImageSequence => ReferencedSOPInstanceUID
            ref_sop_uid_this_frame = None
            if hasattr(frame, "DerivationImageSequence") and len(frame.DerivationImageSequence) > 0:
                deriv_item = frame.DerivationImageSequence[0]
                if hasattr(deriv_item, "SourceImageSequence") and len(deriv_item.SourceImageSequence) > 0:
                    ref_sop_uid_this_frame = getattr(deriv_item.SourceImageSequence[0], "ReferencedSOPInstanceUID", None)

            # image_position_patient -> PlanePositionSequence
            image_position_patient = None
            if hasattr(frame, "PlanePositionSequence") and len(frame.PlanePositionSequence) > 0:
                image_position_patient = getattr(frame.PlanePositionSequence[0], "ImagePositionPatient", None)

            # pixel_data
            if frame_index < pixel_array_3d.shape[0]:
                frame_pixel_data = pixel_array_3d[frame_index, :, :]
            else:
                frame_pixel_data = np.zeros((rows, columns), dtype=pixel_array_3d.dtype)

            frame_dict = {
                "frame_index": frame_index,
                "segment_number": segment_number,
                "segment_name": seg_name,
                "segment_color": seg_color,
                "image_position_patient": image_position_patient,
                "ref_sop_uid": ref_sop_uid_this_frame,
                "pixel_data": frame_pixel_data
            }
            frames.append(frame_dict)
    else:
        # fallback if mismatch
        num_frames = pixel_array_3d.shape[0]
        for frame_index in range(num_frames):
            frame_dict = {
                "frame_index": frame_index,
                "segment_number": None,
                "segment_name": None,
                "segment_color": None,
                "image_position_patient": None,
                "ref_sop_uid": None,
                "pixel_data": pixel_array_3d[frame_index, :, :]
            }
            frames.append(frame_dict)

    final_dict = {
        "segmentation_name": str(segmentation_name),
        "segmentation_type": str(segmentation_type),
        "ref_series_uid": str(ref_series_uid) if ref_series_uid else None,
        "ref_sop_class_uid": str(ref_sop_class_uid) if ref_sop_class_uid else None,
        "pixel_spacing": pixel_spacing,
        "slice_thickness": slice_thickness,
        "spacing_between_slices": spacing_between_slices,
        "image_orientation": image_orientation,
        "rows": rows,
        "columns": columns,
        "num_frames": len(frames),
        "frames": frames
    }

    return final_dict


def main():
    """
    Main script usage:
      python Step_2_3_DecodeSegmentation.py <selected_segmentations_json>

    Or if no arguments, it will prompt the user. The script will:
      - Load the specified "SelectedSegmentations_info.json".
      - For each entry in "selected_segmentations", read the single .dcm file from
        its "assessor_folder_path".
      - Decode the segmentation.
      - Save to:
          segmentations_pickles/EN_{exported_name}_SN_{segmentor_name}_FN_{folder_name}.pkl
          segmentations_pickles/EN_{exported_name}_SN_{segmentor_name}_FN_{folder_name}_withoutImageData.json
        in the same directory as <selected_segmentations_json>.

      - Finally, create "PreparedSegmentations_info.json" in that same directory,
        updating each segmentation in 'selected_segmentations' with:
          * pkl_file
          * json_file
          * num_frames
          * segment_name_count (# distinct segment_name in frames)
          * ref_series_uid (overriding with the DICOM's actual value)
    """
    if len(sys.argv) < 2:
        input_json = input("Enter path to SelectedSegmentations_info.json: ").strip()
    else:
        input_json = sys.argv[1]

    if not os.path.exists(input_json):
        print(f"ERROR: JSON file not found: {input_json}")
        sys.exit(1)

    # Load the selected segmentations
    with open(input_json, "r") as f:
        data = json.load(f)

    selected_segmentations = data.get("selected_segmentations", {})
    if not selected_segmentations:
        print("[INFO] No selected_segmentations found in the JSON. Exiting.")
        sys.exit(0)

    # Create output folder "segmentations_pickles" next to the JSON
    base_dir = os.path.dirname(os.path.abspath(input_json))
    out_dir = os.path.join(base_dir, "segmentations_pickles")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    # Process each selected segmentation
    for folder_name, seg_meta in selected_segmentations.items():
        assessor_path = seg_meta.get("assessor_folder_path", "")
        if not os.path.isdir(assessor_path):
            print(f"Skipping {folder_name} - invalid assessor_folder_path: {assessor_path}")
            continue

        # Typically one .dcm in that folder
        dcm_files = [f for f in os.listdir(assessor_path) if f.lower().endswith(".dcm")]
        if len(dcm_files) == 0:
            print(f"Skipping {folder_name} - no .dcm files found in {assessor_path}")
            continue

        seg_dcm_path = os.path.join(assessor_path, dcm_files[0])

        # Decode
        decoded_dict = decode_segmentation_dcm(seg_dcm_path)

        # Build output filename
        exported_name = seg_meta.get("exported_name", "UnknownExportName").replace(" ", "_")
        segmentor_name = seg_meta.get("segmentor_name", "UnknownSegmentor").replace(" ", "_")
        safe_folder = folder_name.replace(" ", "_")
        out_filename_base = f"EN_{exported_name}_SN_{segmentor_name}_FN_{safe_folder}"

        # 1) Save pickle with full image data
        pkl_path = os.path.join(out_dir, f"{out_filename_base}.pkl")
        with open(pkl_path, "wb") as pklf:
            pickle.dump(decoded_dict, pklf)

        # 2) Create a JSON without pixel_data, then sanitize
        dict_no_image = {}
        for k, v in decoded_dict.items():
            if k != "frames":
                dict_no_image[k] = v
            else:
                frames_no_img = []
                for fr in v:
                    fr_copy = dict(fr)
                    fr_copy.pop("pixel_data", None)  # remove heavy numpy data
                    frames_no_img.append(fr_copy)
                dict_no_image["frames"] = frames_no_img

        dict_json_safe = sanitize_for_json(dict_no_image)
        json_path = os.path.join(out_dir, f"{out_filename_base}_withoutImageData.json")
        with open(json_path, "w") as jf:
            json.dump(dict_json_safe, jf, indent=4)

        print(f"[INFO] Decoded {folder_name} =>")
        print(f"       PKL:  {os.path.basename(pkl_path)}")
        print(f"       JSON: {os.path.basename(json_path)}")

        # -- Prepare extra metadata for final JSON update -- #
        # 1) path to pkl file
        seg_meta["pkl_file"] = pkl_path
        # 2) path to json file
        seg_meta["json_file"] = json_path
        # 3) num_frames
        seg_meta["num_frames"] = decoded_dict.get("num_frames", 0)
        # 4) segment_name_count => distinct non-None "segment_name" in frames
        frames_list = decoded_dict.get("frames", [])
        name_counter = Counter(
            fr.get("segment_name") for fr in frames_list if fr.get("segment_name") is not None
        )
        seg_meta["segment_name_count"] = dict(name_counter)
        # 5) ref_series_uid => override with the one from the DICOM
        seg_meta["ref_series_uid"] = decoded_dict.get("ref_series_uid", None)

    # Save the updated dictionary to a new JSON named "PreparedSegmentations_info.json"
    out_prepared_json_path = os.path.join(base_dir, "PreparedSegmentations_info.json")
    with open(out_prepared_json_path, "w") as f:
        json.dump(data, f, indent=4)

    print(f"[INFO] Prepared segmentations JSON saved to: {out_prepared_json_path}")


if __name__ == "__main__":
    main()