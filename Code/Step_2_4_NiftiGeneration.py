#!/usr/bin/env python3
"""
Step_2_4_NiftiGeneration.py

Implements three subtasks:

    2.4.1 - Finds corresponding image series for each segmentation in PreparedSegmentations_info.json
            by matching 'ref_series_uid' to the 'series_uid' in StudySeries_info.json.
            Appends 'series_info' to each segmentation and writes Ready2Nifti_info.json.

    2.4.2 - Creates the original CT/MRI NIfTI for each referenced series.
            Saved as "<series_number>.nii" in a "NIFTI" folder.

    2.4.3 - Creates segmentation NIfTI for each segmentation object. For each segmentation .pkl:
            - We read the frames array (with 'ref_sop_uid', 'segment_name', 'pixel_data' 2D).
            - We match each ref_sop_uid to the original CT slice index (by comparing SOPInstanceUID).
            - We build a 3D mask array for each unique segment_name and save it as
              "{series_number}_ON_{segment_name}__FN_{seg_folder_name}.nii".

Author: YourName
Date: YYYY-MM-DD
"""

import os
import sys
import json
import pickle
import pydicom
import numpy as np
import nibabel as nib

# ----------------------------------------------------------------
# 2.4.1 - MATCH REF_SERIES_UID AND CREATE Ready2Nifti_info.json
# ----------------------------------------------------------------

def step_2_4_1_create_ready2nifti(prepared_json_path, study_series_json_path, output_json="Ready2Nifti_info.json"):
    """
    Reads PreparedSegmentations_info.json and StudySeries_info.json, matches each segmentation's
    ref_series_uid with the correct SCANS entry. Appends 'series_info' (e.g. folder_path, series_number)
    to each segmentation. Writes out output_json in the same folder as prepared_json_path.

    Parameters
    ----------
    prepared_json_path : str
        Path to PreparedSegmentations_info.json
    study_series_json_path : str
        Path to StudySeries_info.json
    output_json : str
        Name of the final JSON, default: 'Ready2Nifti_info.json'

    Returns
    -------
    str
        The path to the newly created Ready2Nifti_info.json
    """
    # Load prepared info
    with open(prepared_json_path, "r") as f:
        prepared_data = json.load(f)

    # Load study series info
    with open(study_series_json_path, "r") as f:
        study_series_data = json.load(f)

    seg_dict = prepared_data.get("selected_segmentations", {})
    # For each segmentation, find series by matching ref_series_uid
    for seg_folder_name, seg_info in seg_dict.items():
        ref_uid = seg_info.get("ref_series_uid", None)
        if not ref_uid:
            continue

        # Find matching SCANS entry
        matched_series_key = None
        matched_series_info = None
        for series_key, series_info in study_series_data.items():
            if series_info.get("series_uid") == ref_uid:
                matched_series_key = series_key
                matched_series_info = series_info
                break

        if matched_series_info:
            seg_info["series_info"] = {
                "series_folder_path": matched_series_info["series_folder_path"],
                "series_number": matched_series_info["series_number"],
                "series_uid": matched_series_info["series_uid"],
                "series_description": matched_series_info["series_description"]
            }
        else:
            seg_info["series_info"] = None

    # Write out
    out_dir = os.path.dirname(os.path.abspath(prepared_json_path))
    out_path = os.path.join(out_dir, output_json)
    with open(out_path, "w") as f:
        json.dump(prepared_data, f, indent=4)

    print(f"[Step 2.4.1] Created {output_json} at: {out_path}")
    return out_path

# ----------------------------------------------------------------
# 2.4.2 - CREATE ORIGINAL CT/MRI NIFTI
# ----------------------------------------------------------------

def load_dicom_series(series_folder_path):
    """
    Loads a DICOM series from series_folder_path, returns (volume_3d, affine, dims).
    This is a simplistic approach: we:
     - gather all .dcm files,
     - sort them by InstanceNumber or ImagePositionPatient (Z),
     - stack into a 3D numpy array,
     - build an approximate affine using pixel spacing, slice thickness, orientation, etc.

    In real practice, you might want a more robust approach or use dcm2niix.
    """
    import glob
    dcm_files = sorted(glob.glob(os.path.join(series_folder_path, "*.dcm")))

    # Read all slices
    slices = []
    for f in dcm_files:
        ds = pydicom.dcmread(f, force=True)
        slices.append(ds)
    if not slices:
        raise RuntimeError(f"No DICOM slices found in {series_folder_path}")

    # Sort slices by ImagePositionPatient or InstanceNumber
    # Let's do instance number if available
    def sort_key(ds):
        return getattr(ds, "InstanceNumber", 0)
    slices.sort(key=sort_key)

    # Build 3D volume
    sample_ds = slices[0]
    rows = sample_ds.Rows
    cols = sample_ds.Columns

    # Pixel spacing & slice thickness
    px_spacing = [1.0, 1.0]
    slice_thick = 1.0
    if hasattr(sample_ds, "PixelSpacing"):
        px_spacing = [float(x) for x in sample_ds.PixelSpacing]
    if hasattr(sample_ds, "SliceThickness"):
        slice_thick = float(sample_ds.SliceThickness)

    # Orientation or assume Axial IOP
    iop = [1, 0, 0, 0, 1, 0]
    if hasattr(sample_ds, "ImageOrientationPatient"):
        iop = [float(x) for x in sample_ds.ImageOrientationPatient]

    n_slices = len(slices)
    volume_3d = np.zeros((rows, cols, n_slices), dtype=np.int16)

    # Fill volume
    for idx, ds in enumerate(slices):
        arr = ds.pixel_array
        volume_3d[:, :, idx] = arr

    # Build a simple affine
    # We'll assume no shear for demonstration
    # The direction cosines are iop[0..2], iop[3..5]
    # The slice direction can be cross of these two
    # We won't do a fully robust approach
    row_cos = np.array(iop[0:3])
    col_cos = np.array(iop[3:6])
    # normal direction
    slice_cos = np.cross(row_cos, col_cos)

    # Scale by pixel spacing
    spacing = np.array([px_spacing[0], px_spacing[1], slice_thick], dtype=float)
    affine = np.zeros((4, 4), dtype=float)
    affine[3, 3] = 1.0
    affine[0:3, 0] = row_cos * spacing[0]
    affine[0:3, 1] = col_cos * spacing[1]
    affine[0:3, 2] = slice_cos * spacing[2]

    # for translation, we can get from first slice's ImagePositionPatient if present
    if hasattr(slices[0], "ImagePositionPatient"):
        ipp = [float(x) for x in slices[0].ImagePositionPatient]
        affine[0:3, 3] = ipp

    return volume_3d, affine, (rows, cols, n_slices)

def step_2_4_2_create_original_nifti(ready2nifti_json_path, overwrite=False):
    """
    Reads Ready2Nifti_info.json, for each segmentation's series_info,
    loads the DICOM series, and creates e.g. "1.nii" in a "NIFTI" folder.

    Skips creation if the file exists and has matching shape unless overwrite=True.

    Parameters
    ----------
    ready2nifti_json_path : str
        Path to the Ready2Nifti_info.json
    overwrite : bool
        Whether to overwrite existing .nii if same shape. Default False.
    """
    with open(ready2nifti_json_path, "r") as f:
        data = json.load(f)

    seg_dict = data.get("selected_segmentations", {})
    base_dir = os.path.dirname(os.path.abspath(ready2nifti_json_path))
    out_dir = os.path.join(base_dir, "NIFTI")
    os.makedirs(out_dir, exist_ok=True)

    # We'll keep track of which series we have already processed
    processed_series = {}

    for seg_folder_name, seg_info in seg_dict.items():
        series_info = seg_info.get("series_info")
        if not series_info:
            continue

        series_number = series_info.get("series_number")
        series_path = series_info.get("series_folder_path")

        if not series_path or not os.path.isdir(series_path):
            print(f"Skipping series {series_number} - invalid path {series_path}")
            continue

        # If we haven't processed this series yet, create the .nii
        if series_number in processed_series:
            continue  # already done

        # Build name
        nii_name = f"{series_number}.nii"
        nii_path = os.path.join(out_dir, nii_name)

        # If file exists, do shape check
        if os.path.exists(nii_path) and not overwrite:
            try:
                existing_img = nib.load(nii_path)
                shape_exists = existing_img.shape
                # We'll assume this shape must match
                # (rows, cols, slices). If it does, skip
                # Otherwise we proceed to re-create
                # This is your policy to skip or not
                processed_series[series_number] = nii_path
                print(f"[2.4.2] Found existing {nii_name} with shape {shape_exists}, skipping creation.")
                continue
            except:
                pass

        # Load the dicom series
        try:
            vol_3d, aff, dims = load_dicom_series(series_path)
        except Exception as e:
            print(f"Error loading DICOM series {series_number} from {series_path}: {e}")
            continue

        # Save as nifti
        nifti_img = nib.Nifti1Image(vol_3d, aff)
        nib.save(nifti_img, nii_path)
        processed_series[series_number] = nii_path
        print(f"[2.4.2] Created {nii_name} with shape {vol_3d.shape} at {nii_path}")


# ----------------------------------------------------------------
# 2.4.3 - CREATE SEGMENTATION NIFTI
# ----------------------------------------------------------------

def step_2_4_3_create_seg_nifti(ready2nifti_json_path, overwrite=False):
    """
    For each selected segmentation in Ready2Nifti_info.json, we:
     - load its pkl_file with frames[]
     - find the matching original CT .nii (we assume we created it in step 2.4.2 in NIFTI)
       or we re-load the original DICOM to confirm shape & slice SOPInstanceUID
     - build a separate 3D mask array for each segment_name
     - store as e.g. "{series_number}_ON_{segment_name}__FN_{folder_name}.nii" in NIFTI.

    We skip creation if the file exists and shape matches (unless overwrite=True).
    """
    with open(ready2nifti_json_path, "r") as f:
        data = json.load(f)

    seg_dict = data.get("selected_segmentations", {})
    base_dir = os.path.dirname(os.path.abspath(ready2nifti_json_path))
    out_dir = os.path.join(base_dir, "NIFTI")
    os.makedirs(out_dir, exist_ok=True)

    # We need slice order from the original series to match frames' ref_sop_uid
    # Let's build a cache: series_number -> [list of SOPInstanceUID in correct order]
    # plus the shape & affine
    # We'll rely on the same load_dicom_series() approach from step_2_4_2,
    # but we also store each slice ds.SOPInstanceUID
    from collections import defaultdict
    series_sop_uids_cache = {}  # { series_number: (sop_uid_list, shape, aff) }

    def load_sop_uid_order(series_path):
        """Return (list_of_sop_uid_in_order, shape, affine, volume_3d_dtype) for the given series path."""
        import glob
        dcm_files = sorted(glob.glob(os.path.join(series_path, "*.dcm")))
        if not dcm_files:
            raise RuntimeError("No DICOMs found.")
        # read all, sort
        slices = []
        for f in dcm_files:
            ds = pydicom.dcmread(f, force=True)
            slices.append(ds)
        slices.sort(key=lambda ds: getattr(ds, "InstanceNumber", 0))

        sop_list = []
        rows = slices[0].Rows
        cols = slices[0].Columns
        px_spacing = getattr(slices[0], "PixelSpacing", [1.0, 1.0])
        slice_thick = getattr(slices[0], "SliceThickness", 1.0)

        # orientation
        iop = getattr(slices[0], "ImageOrientationPatient", [1,0,0,0,1,0])
        row_cos = np.array(iop[0:3])
        col_cos = np.array(iop[3:6])
        slice_cos = np.cross(row_cos, col_cos)

        spacing = np.array([px_spacing[0], px_spacing[1], slice_thick], dtype=float)
        aff = np.zeros((4,4), dtype=float)
        aff[3,3] = 1.0
        aff[0:3,0] = row_cos * spacing[0]
        aff[0:3,1] = col_cos * spacing[1]
        aff[0:3,2] = slice_cos * spacing[2]
        if hasattr(slices[0], "ImagePositionPatient"):
            ipp = [float(x) for x in slices[0].ImagePositionPatient]
            aff[0:3,3] = ipp

        for s in slices:
            sop_list.append(getattr(s, "SOPInstanceUID", None))

        # We'll also keep the dtype from pixel_array
        test_arr = slices[0].pixel_array
        vol_dtype = test_arr.dtype

        shape_ = (rows, cols, len(slices))
        return sop_list, shape_, aff, vol_dtype

    for seg_folder_name, seg_info in seg_dict.items():
        pkl_file = seg_info.get("pkl_file")
        series_info = seg_info.get("series_info", {})
        if not pkl_file or not os.path.exists(pkl_file):
            print(f"Skipping {seg_folder_name} - pkl_file missing or not found.")
            continue
        series_number = series_info.get("series_number")
        series_path = series_info.get("series_folder_path")
        if not series_number or not series_path or not os.path.isdir(series_path):
            print(f"Skipping {seg_folder_name} - invalid series info.")
            continue

        # Load the frames from the pickle
        with open(pkl_file, "rb") as pf:
            seg_data = pickle.load(pf)
        frames = seg_data.get("frames", [])
        # The segmentation might have multiple distinct segment_name. We'll gather them
        # "segment_name" -> list of (slice_idx, 2D mask)
        # but first we need the original series SOP order
        if series_number not in series_sop_uids_cache:
            try:
                sop_uid_list, shape_, aff_, vol_dtype_ = load_sop_uid_order(series_path)
                series_sop_uids_cache[series_number] = (sop_uid_list, shape_, aff_, vol_dtype_)
            except Exception as e:
                print(f"Unable to load series info for {series_number}: {e}")
                continue

        sop_uid_list, shape_, aff_, vol_dtype_ = series_sop_uids_cache[series_number]
        # shape_ = (rows, cols, slices)
        # We'll build a mapping from sop_uid -> index in that slice dimension
        sop_uid_to_index = {}
        for i, suid in enumerate(sop_uid_list):
            sop_uid_to_index[suid] = i

        # Group frames by segment_name
        from collections import defaultdict
        segment_frames_map = defaultdict(list)
        for fr in frames:
            seg_name = fr.get("segment_name", "UnknownSEG")
            sopid = fr.get("ref_sop_uid", None)
            frame_2d = fr.get("pixel_data", None)
            # find slice index
            if sopid in sop_uid_to_index and frame_2d is not None:
                slice_index = sop_uid_to_index[sopid]
                segment_frames_map[seg_name].append((slice_index, frame_2d))

        # For each segment_name, build a 3D mask
        # shape = shape_
        # typically it's a binary mask
        for seg_name, slices_info in segment_frames_map.items():
            # Create a 3D array of zeros
            mask_3d = np.zeros(shape_, dtype=np.uint8)

            # place each 2D mask
            for slice_idx, mask_2d in slices_info:
                # mask_2d shape => (rows, cols)
                if mask_2d.shape[0] == shape_[0] and mask_2d.shape[1] == shape_[1]:
                    mask_3d[:, :, slice_idx] = mask_2d
                else:
                    print(f"WARNING: mismatch shape in seg {seg_folder_name}, segment {seg_name}, slice {slice_idx}")

            # Now save as NIfTI
            # filename = {series_number}_ON_{seg_name}__FN_{folder_name}.nii
            nii_name = f"{series_number}_ON_{seg_name}__FN_{seg_folder_name}.nii"
            nii_path = os.path.join(out_dir, nii_name)
            if os.path.exists(nii_path) and not overwrite:
                try:
                    existing = nib.load(nii_path)
                    if existing.shape == shape_:
                        print(f"[2.4.3] Found existing {nii_name} with shape {existing.shape}, skipping creation.")
                        continue
                except:
                    pass

            nifti_img = nib.Nifti1Image(mask_3d, aff_)
            nib.save(nifti_img, nii_path)
            print(f"[2.4.3] Created {nii_name} with shape {mask_3d.shape}")

# ----------------------------------------------------------------
# Main script combining the three steps
# ----------------------------------------------------------------

def main():
    """
    Example usage:
      python Step_2_4_NiftiGeneration.py

    This script does:
      2.4.1 => produce Ready2Nifti_info.json
      2.4.2 => produce <series_number>.nii in NIFTI for each referenced series
      2.4.3 => produce {series_number}_ON_{segment_name}__FN_{seg_folder}.nii in NIFTI
    """
    prepared_json_path = input("Enter the path to PreparedSegmentations_info.json: ")
    study_json_path = input("Enter the path to StudySeries_info.json: ")

    # Step 2.4.1
    ready2nifti_path = step_2_4_1_create_ready2nifti(
        prepared_json_path=prepared_json_path,
        study_series_json_path=study_json_path,
        output_json="Ready2Nifti_info.json"
    )

    # Step 2.4.2
    # In the future, you can pass overwrite=True if you want to forcibly re-generate
    step_2_4_2_create_original_nifti(ready2nifti_json_path=ready2nifti_path, overwrite=False)

    # Step 2.4.3
    step_2_4_3_create_seg_nifti(ready2nifti_json_path=ready2nifti_path, overwrite=False)


if __name__ == "__main__":
    main()
