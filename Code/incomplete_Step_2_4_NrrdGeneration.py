#!/usr/bin/env python3
"""
Step_2_4_NrrdGeneration.py

Implements three subtasks:

    2.4.1 - Finds corresponding image series for each segmentation in PreparedSegmentations_info.json
            by matching 'ref_series_uid' to the 'series_uid' in StudySeries_info.json.
            Appends 'series_info' to each segmentation and writes Ready2Nifti_info.json.

    2.4.2 - Creates the original CT/MRI volume as a NRRD file.
            Saved as "<series_number>.nrrd" in a folder named "NRRD".

    2.4.3 - Creates segmentation NRRD files for each segmentation object.
            For each segmentation pickle:
              - Reads the frames array (with 'ref_sop_uid', 'segment_name', 'pixel_data').
              - Matches each ref_sop_uid to the original CT slice index (via SOPInstanceUID).
              - Builds a 3D mask array for each unique segment_name.
              - Saves each as "{series_number}_ON_{segment_name}__FN_{seg_folder_name}.seg.nrrd"
                in the "NRRD" folder, with custom header fields.

Author: YourName
Date: YYYY-MM-DD

Note: Requires pynrrd (install via: pip install pynrrd)
"""

import os
import sys
import json
import pickle
import pydicom
import numpy as np
import nibabel as nib  # only used for affine extraction, if needed
import nrrd           # requires: pip install pynrrd

# ----------------------------------------------------------------
# 2.4.1 - MATCH REF_SERIES_UID AND CREATE Ready2Nifti_info.json
# ----------------------------------------------------------------

def step_2_4_1_create_ready2nifti(prepared_json_path, study_series_json_path, output_json="Ready2Nifti_info.json"):
    """
    Reads PreparedSegmentations_info.json and StudySeries_info.json, matches each segmentation's
    ref_series_uid with the corresponding SCANS entry, appends 'series_info' to each segmentation,
    and writes out output_json in the same folder as prepared_json_path.

    Returns the path to the created Ready2Nifti_info.json.
    """
    with open(prepared_json_path, "r") as f:
        prepared_data = json.load(f)
    with open(study_series_json_path, "r") as f:
        study_series_data = json.load(f)
    seg_dict = prepared_data.get("selected_segmentations", {})
    for seg_folder_name, seg_info in seg_dict.items():
        ref_uid = seg_info.get("ref_series_uid", None)
        if not ref_uid:
            continue
        matched_series_info = None
        for series_info in study_series_data.values():
            if series_info.get("series_uid") == ref_uid:
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
    out_dir = os.path.dirname(os.path.abspath(prepared_json_path))
    out_path = os.path.join(out_dir, output_json)
    with open(out_path, "w") as f:
        json.dump(prepared_data, f, indent=4)
    print(f"[2.4.1] Created {output_json} at: {out_path}")
    return out_path

# ----------------------------------------------------------------
# 2.4.2 - CREATE ORIGINAL CT/MRI NRRD
# ----------------------------------------------------------------

def load_dicom_series(series_folder_path):
    """
    Loads a DICOM series from series_folder_path.
    Returns (volume_3d, affine, dims).
    """
    import glob
    dcm_files = sorted(glob.glob(os.path.join(series_folder_path, "*.dcm")))
    slices = []
    for f in dcm_files:
        ds = pydicom.dcmread(f, force=True)
        slices.append(ds)
    if not slices:
        raise RuntimeError(f"No DICOM slices found in {series_folder_path}")
    def sort_key(ds): return getattr(ds, "InstanceNumber", 0)
    slices.sort(key=sort_key)
    sample_ds = slices[0]
    rows, cols = sample_ds.Rows, sample_ds.Columns
    px_spacing = [1.0, 1.0]
    slice_thick = 1.0
    if hasattr(sample_ds, "PixelSpacing"):
        px_spacing = [float(x) for x in sample_ds.PixelSpacing]
    if hasattr(sample_ds, "SliceThickness"):
        slice_thick = float(sample_ds.SliceThickness)
    iop = [1, 0, 0, 0, 1, 0]
    if hasattr(sample_ds, "ImageOrientationPatient"):
        iop = [float(x) for x in sample_ds.ImageOrientationPatient]
    n_slices = len(slices)
    volume_3d = np.zeros((rows, cols, n_slices), dtype=np.int16)
    for idx, ds in enumerate(slices):
        volume_3d[:, :, idx] = ds.pixel_array
    row_cos = np.array(iop[0:3])
    col_cos = np.array(iop[3:6])
    slice_cos = np.cross(row_cos, col_cos)
    spacing = np.array([px_spacing[0], px_spacing[1], slice_thick], dtype=float)
    affine = np.zeros((4,4), dtype=float)
    affine[3,3] = 1.0
    affine[0:3,0] = row_cos * spacing[0]
    affine[0:3,1] = col_cos * spacing[1]
    affine[0:3,2] = slice_cos * spacing[2]
    if hasattr(slices[0], "ImagePositionPatient"):
        ipp = [float(x) for x in slices[0].ImagePositionPatient]
        affine[0:3,3] = ipp
    dims = (rows, cols, n_slices)
    return volume_3d, affine, dims

def step_2_4_2_create_original_nrrd(ready2nifti_json_path, overwrite=False):
    """
    Reads Ready2Nifti_info.json, for each segmentation's series_info,
    loads the DICOM series, and creates a .nrrd file (e.g. "1.nrrd") in a folder named "NRRD".

    Skips creation if the file exists with matching shape unless overwrite is True.
    """
    with open(ready2nifti_json_path, "r") as f:
        data = json.load(f)
    seg_dict = data.get("selected_segmentations", {})
    base_dir = os.path.dirname(os.path.abspath(ready2nifti_json_path))
    out_dir = os.path.join(base_dir, "NRRD")
    os.makedirs(out_dir, exist_ok=True)
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
        if series_number in processed_series:
            continue
        nrrd_name = f"{series_number}.nrrd"
        nrrd_path = os.path.join(out_dir, nrrd_name)
        if os.path.exists(nrrd_path) and not overwrite:
            try:
                import nrrd
                header_existing, data_existing = nrrd.read(nrrd_path)
                if data_existing.shape == tuple(load_dicom_series(series_path)[2]):
                    processed_series[series_number] = nrrd_path
                    print(f"[2.4.2] Found existing {nrrd_name} with shape {data_existing.shape}, skipping creation.")
                    continue
            except Exception as e:
                pass
        try:
            vol_3d, aff, dims = load_dicom_series(series_path)
        except Exception as e:
            print(f"Error loading DICOM series {series_number} from {series_path}: {e}")
            continue
        # Build NRRD header from affine and dims.
        # Convert affine to space directions and origin.
        directions = [aff[0:3,0].tolist(), aff[0:3,1].tolist(), aff[0:3,2].tolist()]
        origin = aff[0:3,3].tolist()
        header = {
            "space directions": directions,
            "space origin": origin,
            "sizes": dims,
            "type": "short"
        }
        try:
            import nrrd
            nrrd.write(nrrd_path, vol_3d, header)
            processed_series[series_number] = nrrd_path
            print(f"[2.4.2] Created {nrrd_name} with shape {vol_3d.shape} at {nrrd_path}")
        except Exception as e:
            print(f"Error writing NRRD for series {series_number}: {e}")

# ----------------------------------------------------------------
# 2.4.3 - CREATE SEGMENTATION NRRD
# ----------------------------------------------------------------

def step_2_4_3_create_seg_nrrd(ready2nifti_json_path, overwrite=False):
    """
    For each selected segmentation in Ready2Nifti_info.json, we:
      - Load its pkl_file with frames[].
      - Find the matching original CT .nrrd (created in step 2.4.2 in NRRD folder)
        or reload the original DICOM to confirm shape & slice order.
      - For each unique segment_name, build a 3D mask array.
      - Save as "{series_number}_ON_{segment_name}__FN_{seg_folder_name}.seg.nrrd" in the "NRRD" folder.
      - Additional custom header fields are added to store segmentation metadata.
    """
    with open(ready2nifti_json_path, "r") as f:
        data = json.load(f)
    seg_dict = data.get("selected_segmentations", {})
    base_dir = os.path.dirname(os.path.abspath(ready2nifti_json_path))
    out_dir = os.path.join(base_dir, "NRRD")
    os.makedirs(out_dir, exist_ok=True)

    from collections import defaultdict
    series_sop_uids_cache = {}
    def load_sop_uid_order(series_path):
        import glob
        dcm_files = sorted(glob.glob(os.path.join(series_path, "*.dcm")))
        if not dcm_files:
            raise RuntimeError("No DICOMs found.")
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

        with open(pkl_file, "rb") as pf:
            seg_data = pickle.load(pf)
        frames = seg_data.get("frames", [])
        if series_number not in series_sop_uids_cache:
            try:
                sop_uid_list, shape_, aff_, vol_dtype_ = load_sop_uid_order(series_path)
                series_sop_uids_cache[series_number] = (sop_uid_list, shape_, aff_, vol_dtype_)
            except Exception as e:
                print(f"Unable to load series info for {series_number}: {e}")
                continue

        sop_uid_list, shape_, aff_, vol_dtype_ = series_sop_uids_cache[series_number]
        sop_uid_to_index = {suid: i for i, suid in enumerate(sop_uid_list)}

        from collections import defaultdict
        segment_frames_map = defaultdict(list)
        for fr in frames:
            seg_name = fr.get("segment_name", "UnknownSEG")
            sopid = fr.get("ref_sop_uid", None)
            frame_2d = fr.get("pixel_data", None)
            if sopid in sop_uid_to_index and frame_2d is not None:
                slice_index = sop_uid_to_index[sopid]
                segment_frames_map[seg_name].append((slice_index, frame_2d))

        for seg_name, slices_info in segment_frames_map.items():
            mask_3d = np.zeros(shape_, dtype=np.uint8)
            for slice_idx, mask_2d in slices_info:
                if mask_2d.shape[0] == shape_[0] and mask_2d.shape[1] == shape_[1]:
                    mask_3d[:, :, slice_idx] = mask_2d
                else:
                    print(f"WARNING: mismatch shape in {seg_folder_name}, segment {seg_name}, slice {slice_idx}")
            nii_name = f"{series_number}_ON_{seg_name}__FN_{seg_folder_name}.seg.nrrd"
            nii_path = os.path.join(out_dir, nii_name)
            if os.path.exists(nii_path) and not overwrite:
                try:
                    import nrrd
                    header_existing, data_existing = nrrd.read(nii_path)
                    if tuple(data_existing.shape) == shape_:
                        print(f"[2.4.3] Found existing {nii_name} with shape {data_existing.shape}, skipping creation.")
                        continue
                except:
                    pass

            # Build custom header with segmentation metadata
            header = {
                "space directions": [aff_[0:3,0].tolist(), aff_[0:3,1].tolist(), aff_[0:3,2].tolist()],
                "space origin": aff_[0:3,3].tolist(),
                "sizes": shape_,
                "type": "uchar",
                # Custom fields for segmentation
                "Segmentation_SourceRepresentation": "Binary labelmap",
                "Segmentation_ContainedRepresentationNames": "Binary labelmap"
            }
            # For this segment, we add fields with index 0 (since each file is one segment)
            # You could customize these further.
            # For extent, compute nonzero bounds.
            nz = np.nonzero(mask_3d)
            if nz[0].size > 0:
                extent = f"{int(np.min(nz[0]))} {int(np.max(nz[0]))} " \
                         f"{int(np.min(nz[1]))} {int(np.max(nz[1]))} " \
                         f"{int(np.min(nz[2]))} {int(np.max(nz[2]))}"
            else:
                extent = "0 0 0 0 0 0"
            header.update({
                "Segment0_Name": seg_name,
                "Segment0_NameAutoGenerated": "0",
                "Segment0_Color": "0.5 0.5 0.5",  # default; update if you have color info
                "Segment0_ColorAutoGenerated": "1",
                "Segment0_Extent": extent,
                "Segment0_Layer": "0",
                "Segment0_LabelValue": "1"
            })
            try:
                import nrrd
                nrrd.write(nii_path, mask_3d, header)
                print(f"[2.4.3] Created {nii_name} with shape {mask_3d.shape}")
            except Exception as e:
                print(f"Error writing NRRD segmentation for {seg_folder_name}, segment {seg_name}: {e}")

# ----------------------------------------------------------------
# Main script combining the three steps
# ----------------------------------------------------------------

def main():
    """
    Example usage:
      python Step_2_4_NrrdGeneration.py

    This script does:
      2.4.1 => produce Ready2Nifti_info.json (unchanged)
      2.4.2 => produce <series_number>.nrrd in NRRD for each referenced series
      2.4.3 => produce {series_number}_ON_{segment_name}__FN_{seg_folder_name}.seg.nrrd in NRRD
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
    step_2_4_2_create_original_nrrd(ready2nifti_json_path=ready2nifti_path, overwrite=False)

    # Step 2.4.3
    step_2_4_3_create_seg_nrrd(ready2nifti_json_path=ready2nifti_path, overwrite=False)

if __name__ == "__main__":
    main()