#!/usr/bin/env python3
"""
ConcatMultiplObjects.py

Merges multiple segmentation objects (pixel_data) into new segmentation objects based on a merge plan.
The merge plan is read from a JSON file named "merge_plan.json" located in the same directory
as PreparedSegmentations_info.json unless explicitly provided.
If no merge plan is found or if it's empty, the user is prompted to define one interactively.

Usage:
    python ConcatMultiplObjects.py --prepared_json /path/to/PreparedSegmentations_info.json [--merge_plan /path/to/merge_plan.json]

Example merge_plan.json structure:
{
  "merge_plan": {
    "SEG_20241021_181708_943_S2": [
      { "old_objects": ["MPD", "P", "M"], "new_object": "Pancreas" },
      { "old_objects": ["CHA", "SMA", "CA"], "new_object": "Arteries" }
    ],
    "SEG_20240910_110819_524_S4": [
      { "old_objects": ["MPD", "P", "M"], "new_object": "Pancreas" }
    ],
    "all": [
      { "old_objects": ["CHA", "SMA", "CA"], "new_object": "Arteries" }
    ]
  }
}

Author: YourName
Date: YYYY-MM-DD
"""

import os
import sys
import json
import pickle
import argparse
import numpy as np

def parse_args():
    parser = argparse.ArgumentParser(
        description="Merge segmentation objects based on a merge plan."
    )
    parser.add_argument(
        "--prepared_json", required=False,
        help="Path to PreparedSegmentations_info.json"
    )
    parser.add_argument(
        "--merge_plan", required=False,
        help="(Optional) Path to merge_plan.json. If not provided, defaults to the same directory as PreparedSegmentations_info.json."
    )
    return parser.parse_args()

def define_merge_plan_interactively():
    """
    Interactively ask the user to define a merge plan.
    The user can choose a global plan (applied to all segmentations) or
    a specific plan for selected segmentation folders.
    
    Returns:
        dict: A merge_plan dictionary.
    """
    merge_plan = {}
    print("\nNo merge plan found. Would you like to define one interactively? (y/n)")
    resp = input(">> ").strip().lower()
    if resp != "y":
        return merge_plan  # empty

    print("Do you want to define a global merge plan for all segmentations? (y/n)")
    global_resp = input(">> ").strip().lower()
    if global_resp == "y":
        old_objs_input = input("Enter old segmentation object names to merge (comma-separated): ").strip()
        new_obj = input("Enter new segmentation object name: ").strip()
        if old_objs_input and new_obj:
            merge_plan["all"] = [
                {
                    "old_objects": [x.strip() for x in old_objs_input.split(",") if x.strip()],
                    "new_object": new_obj
                }
            ]
    else:
        print("Now, enter merge directives for specific segmentation folders.")
        while True:
            seg_key = input("Enter segmentation folder key (or leave blank to finish): ").strip()
            if not seg_key:
                break
            old_objs_input = input(f"Enter old segmentation object names for {seg_key} (comma-separated): ").strip()
            new_obj = input(f"Enter new segmentation object name for {seg_key}: ").strip()
            if old_objs_input and new_obj:
                merge_plan.setdefault(seg_key, []).append({
                    "old_objects": [x.strip() for x in old_objs_input.split(",") if x.strip()],
                    "new_object": new_obj
                })
            else:
                print("Invalid entry, skipping.")
    return merge_plan

def main():
    args = parse_args()
    
    # Determine paths
    if not args.prepared_json:
        prepared_json_path = input("Please provide the path to PreparedSegmentations_info.json: ").strip()
    else:
        prepared_json_path = args.prepared_json

    if args.merge_plan:
        merge_plan_path = args.merge_plan
    else:
        merge_plan_path = os.path.join(os.path.dirname(os.path.abspath(prepared_json_path)), "merge_plan.json")

    if not os.path.exists(prepared_json_path):
        print(f"Error: Cannot find PreparedSegmentations_info.json at {prepared_json_path}")
        sys.exit(1)

    # Load PreparedSegmentations_info.json
    with open(prepared_json_path, "r") as f:
        prepared_data = json.load(f)
    seg_dict = prepared_data.get("selected_segmentations", {})
    if not seg_dict:
        print("[INFO] No selected_segmentations found. Exiting.")
        sys.exit(0)

    # Load merge plan if exists; otherwise, define interactively
    if os.path.exists(merge_plan_path):
        with open(merge_plan_path, "r") as f:
            plan_data = json.load(f)
        merge_plan = plan_data.get("merge_plan", {})
    else:
        merge_plan = {}

    if not merge_plan:
        merge_plan = define_merge_plan_interactively()
        if merge_plan:
            # Optionally, save the new merge plan to merge_plan.json for future use.
            with open(merge_plan_path, "w") as f:
                json.dump({"merge_plan": merge_plan}, f, indent=4)
            print(f"[INFO] Saved new merge plan to {merge_plan_path}")
        else:
            print("No merge plan defined. Exiting.")
            sys.exit(0)

    # Process each segmentation folder in the merge plan.
    # Global merges under the "all" key will be applied to every segmentation.
    global_merges = merge_plan.get("all", [])
    
    for seg_folder_name, seg_info in seg_dict.items():
        # Get folder-specific merges if any.
        folder_merges = merge_plan.get(seg_folder_name, [])
        # Combine folder-specific with global merges.
        merges_for_this_seg = folder_merges + global_merges
        if not merges_for_this_seg:
            continue

        pkl_file_path = seg_info.get("pkl_file")
        if not pkl_file_path or not os.path.exists(pkl_file_path):
            print(f"[WARN] {seg_folder_name} has an invalid or missing pkl_file: {pkl_file_path}. Skipping.")
            continue

        print(f"\n[INFO] Processing merges for {seg_folder_name} (pkl: {pkl_file_path})")

        # Load the segmentation pickle
        with open(pkl_file_path, "rb") as pf:
            seg_data = pickle.load(pf)
        frames = seg_data.get("frames", [])
        if not isinstance(frames, list):
            print(f"[ERROR] 'frames' is not a list in {pkl_file_path}. Skipping.")
            continue

        # Determine new segment_number (max existing + 1)
        existing_seg_numbers = [fr.get("segment_number") for fr in frames if fr.get("segment_number") is not None]
        max_seg_num = max(existing_seg_numbers) if existing_seg_numbers else 0

        # Process each merge directive for this segmentation folder
        for merge_item in merges_for_this_seg:
            old_objects = merge_item.get("old_objects", [])
            new_object_name = merge_item.get("new_object")
            if not old_objects or not new_object_name:
                print(f"[WARN] Invalid merge entry {merge_item} in {seg_folder_name}. Skipping.")
                continue

            # Summation: group frames by (ref_sop_uid, image_position_patient)
            slice_map = {}
            for fr in frames:
                seg_name = fr.get("segment_name")
                if seg_name not in old_objects:
                    continue
                px_data = fr.get("pixel_data")
                ref_sop_uid = fr.get("ref_sop_uid")
                ipp = fr.get("image_position_patient")
                if px_data is None or ref_sop_uid is None:
                    continue
                key = (ref_sop_uid, tuple(ipp) if ipp else None)
                if key not in slice_map:
                    slice_map[key] = np.zeros(px_data.shape, dtype=px_data.dtype)
                slice_map[key] += px_data

            # Clip summed mask to binary (max 1)
            for key in slice_map:
                np.clip(slice_map[key], 0, 1, out=slice_map[key])

            # Assign a new segment_number
            max_seg_num += 1
            new_seg_num = max_seg_num

            # Build new frames for the merged object
            new_frames = []
            start_index = len(frames)
            i = 0
            for (ref_sop_uid, ipp), sum_mask in slice_map.items():
                if not np.any(sum_mask):
                    continue
                new_frame = {
                    "frame_index": start_index + i,
                    "segment_number": new_seg_num,
                    "segment_name": new_object_name,
                    "segment_color": None,  # Optionally, allow user to specify a color
                    "image_position_patient": list(ipp) if ipp else None,
                    "ref_sop_uid": ref_sop_uid,
                    "pixel_data": sum_mask
                }
                new_frames.append(new_frame)
                i += 1

            if not new_frames:
                print(f"[INFO] Merge for objects {old_objects} into '{new_object_name}' produced no frames. Skipping.")
                continue

            # Append new frames to existing ones
            frames.extend(new_frames)
            seg_data["frames"] = frames
            seg_data["num_frames"] = len(frames)

            # Update segment_name_count in the JSON
            seg_name_count = seg_info.get("segment_name_count", {})
            seg_name_count[new_object_name] = len(new_frames)
            seg_info["segment_name_count"] = seg_name_count
            seg_info["num_frames"] = seg_data["num_frames"]

            print(f"[INFO] Merged objects {old_objects} into '{new_object_name}' with new segment_number {new_seg_num}. Added {len(new_frames)} frames.")

        # After processing all merges for this segmentation, overwrite the pickle
        with open(pkl_file_path, "wb") as pf:
            pickle.dump(seg_data, pf)
        print(f"[INFO] Updated pickle for {seg_folder_name} at {pkl_file_path}")

    # Finally, overwrite the PreparedSegmentations_info.json with the updated data
    with open(prepared_json_path, "w") as f:
        json.dump(prepared_data, f, indent=4)
    print(f"\n[DONE] Merge plan applied. Updated {prepared_json_path}")

if __name__ == "__main__":
    main()