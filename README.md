> This is part of [Clinician Guide to AI Project Management in Medical Imaging](https://github.com/Sdamirsa/Clinician-Guide-to-AI-Project-Management-in-Medical-Imaging). 

This repo contains the code to turn a folder from XNAT (having SCANS and ASSESSORS folders) to nifti for images and segmentations. We will read the single .dcm segmentation, decode it, find the corresponding image data (X, Y, Z positioning or UID), and save them as nifti files.  

# 1. Problem Definition

When you use an XNAT server, it stores imaging data (in my case CT scan and MRI) inside a SCANS folder (and each series is in a sub-folder named as assigned series number). When you start segmentation of images in the server and export it, it will save each saved segmentation in the ASSESSORS folder in a special (the most positive way to describe it) format. All segmentations are stacked (for example 4 slices with pancreas and 5 with stomach would be one .dcm file with 9 slices). If you want to backup your data into your local and use it in other pipelines, or even view it for validation, you can't do this.

This guide and code would help you, as it's been 2 years that I'm struggling with XNAT structure. And before diving deeper, you can see my project at www.PanCanAID.com, and BIG THANKS to XNAT for making segmentation easier. I hope this guide can make it even better. 

# 1.1. Understanding XNAT segmentation (single .dcm) structure

Dicom files are really multi-level complex dictionaries. When you upload your data to XNAT it will assign new UID for the whole CT/MRI study (named: SOP Class UID), each dicom series (named: series instance UID), and slice (named: SOP instance UID). So if you want to play with your original CT scan and not the version that is uploaded to your XNAT server, the best solution is to store/create a dictionary mapping these things from the CT scan on your device and the one on the XNAT. This is due to the fact that XNAT will pseudonymize your cases. 

If you don't have this, and know the case number and series number, I have a trick to find the corresponding slice in the series (I used something called (0020,0032) Image Position Patient) by finding the X, Y, Z coordinate of the slice of segmentation (e.g. -144.65625\-335.65625\-690.4) and find the same slice in the original CT in my local. 

To be honest, my experience is to just upload the cases to XNAT, and then download them again. It may seem not that much smart, but it is error proof. 

Ok, so let's move on to the SPECIAL (if I want to be positive) structure of segmentations done on XNAT. All of the segmentation will be stored on one single .dcm file. So all segmentation objects (for example pancreas, stomach, ...) and all slices of each mask object (for example pancreas can be visible on 5 slices) will be stacked on top of each other. The ultimate goal is to find, for each slice, the mask name, corresponding slice in the original CT, and pixel data. We also need the corresponding series in the CT scan study, and the name the segmentor assigned to his/her segmentation. 

Before starting the guide, and for providing initial preparation:
- The pixel array is stored in a list
- The segmentation object names are stored as segmentation numbers. We should find the corresponding segmentation name for this number so we can understand the object name. 
- To find the corresponding series and slice, we should find the referenced series UID and referenced slice UID. 
- Also, there is another way to find the corresponding slice by finding the X, Y, and Z coordinate of the image using Image Position Patient (definition: specifies the x, y, and z coordinates of the upper left-hand corner of this 2D slice image). I think this is the best option, as you may want to use your segmentation on different dicom series, and avoid doing image fusion or registration. IDK, who knows what would be the best for your case. 

- IMPORTANT: you need to enter some dicom TAGs, to reach another dicom TAG, and maybe another one, so you can finally reach the value you want. It's like a box, inside a box, and inside a box. You should open the first one, and then the second, and so on. When I define one object as multiple levels, you should first open the first object, and then the second one. 

- Last thing, when I say store as list, you should store as a list considering the order of the objects. Lists in python are ordered, but just remember this point, as we are merging different lists together, so if the order doesn't match, the whole thing would fail. And there is no way to code this better (you can't with this structure). When I say loop and do something, it means that there are multiple similar objects you should loop and open all of them and turn them into a desired format. 

# 2. Solution

The whole solution will get one XNAT folder, structured with a SCANS folder and an ASSESSORS folder. This is the structure (downloaded from the server directly with FTP, instead of using the XNAT desktop client). We had 10 segmentations (from different persons or a modified version of a previous segmentation). You can donwload the same structure by playing with the options of XNAT-Desktop-Client (checking the box for folder structure). 

```
2072
├───ASSESSORS
│   ├───SEG_20240118_235251_213_S2
│   │   └───SEG
            each seg file has these files:
            one SEG_20240118_235251_213_S2.dcm file (with stacked mask objects)
            one SEG_catalog.xml file 
│   ├───SEG_20240710_180044_492_S2
│   │   └───SEG
│   ├───SEG_20240723_214043_238_S2
│   │   └───SEG
│   ├───SEG_20240821_132059_407_S4
│   │   └───SEG
│   ├───SEG_20240826_202611_358_S4
│   │   └───SEG
│   ├───SEG_20240910_110819_524_S4
│   │   └───SEG
│   ├───SEG_20241020_130224_332_S2
│   │   └───SEG
│   ├───SEG_20241020_141205_899_S2
│   │   └───SEG
│   ├───SEG_20241021_181708_943_S2
│   │   └───SEG
│   └───SEG_20241024_192540_108_S2
│       └───SEG
└───SCANS
    ├───1
    │   └───DICOM
                each seg file has these files:
                each slice stored as one .dcm file so we have mutliple .dcm files
                there is usually one .xml file like scan_1_catalog.xml with the series UID and slice UID
    ├───2
    │   └───DICOM
    ├───3
    │   └───DICOM
    ├───4
    │   └───DICOM
    ├───5
    │   └───DICOM
    ├───602
    │   └───DICOM
    └───603
        └───DICOM
2073
    ...
2074
    ...
```

This code takes a folder path for a study object and stores information in a different output path without modifying or writing information to the original folder. The steps of the solution are:
- At the beginning of execution, we will read the entire folder to create a JSON file containing folder information, including scans info (series UID of each folder) and segmentation info (segmentation name defined by the user, date of segmentation, and username of the segmentor for each segmentation folder). Defined in section 2.1. 
- **\[optional\] Definition of the correct segmentation(s)**: Ask the user if they want to select one segmentation (using the name defined by the segmentor or the name of the segmentation folder). This section doesn't have any guide, as it is clear. 
Optionally, the user can provide a path to an Excel file with a column for case number and a column for a list of segmentation names (this should be a list stored as a string or just one string value). Defined in section 2.2. 
- **Decoding the segmentation**: Reading the single (.dcm) file inside each segmentation folder in the ASSESSORS folder, and storing the image data and metadata as pickle. **This is the most important contribution, I think. Defined in section 2.3**.
- **Find corresponding image,  create original nifti**: Finding the corresponding series in the SCANS folder and storing the original image data of that series as nifti.  Then, turns the previous segmentation pickle to nifti considering the original image slices (for each segmentation object separately). This will generate a segmentation nifti with a unified space (so both original and segmentation niftis would have a similar length/height). Defined in section 2.4.
- **\[Optional\]: Merge (sum) multiple segmentation objects**: As the segmentation type is binary, sometimes you should sum multiple objects. For example, in our case, we should sum the pancreas, mass, and main pancreatic duct (if available) to have the real segmentation of the pancreas organ. Defined in section 2.5.
- The last step is our prayer to those who are working with medical imaging, not just to publish, but to make something meaningful for people :)

The structure of the output folder at the end would be like this:

```
2072
├───StudySeries_info.json
├───Segmentations_info.json
└───Segmentations
    ├───EN_verified_SN_sdamirsa_SEG_20240118_235251_213_S2
    │   └───P.pkl
    │   └───G.pkl
    └───EN_initialAAA_SN_sdamirsa_SEG_20241020_130224_332_S2
        └───P.pkl
        └───M.pkl
        └───MPD.pkl
└───Curated_Output
    ├───2.nii
    ├───2_ON_P_FN_SEG_20240118_235251_213_S2.nii
    ├───2_ON_G_FN_SEG_20240118_235251_213_S2.nii
    ├───2_ON_P_FN_SEG_20241020_130224_332_S2.nii
    ├───2_ON_M_FN_SEG_20241020_130224_332_S2.nii
    └───2_ON_MPD_FN_SEG_20241020_130224_332_S2.nii

Note: The segmentations folder include selected segmentations (or all segmentations if haven't defined). Each segmentation folde has a structure of:
    EN_{the name user defined when exporing/saving}_SN_{username_of_segmentor}_FN_{ segmentaiton folder name}.pkl

Note: P, G, .. is the name of the masks the segmentor defined. 

Note: The name of segmentaiton objects are saved as:
    {refrenced series number}_ON_{object name}__FN_{name of segmentation folder}

Note: we only have 2.nii as this was the only series that was used for segmentation. 
```

## 2.0. Installation of libraries 
> ✅ (code)

We will use pydciom to play with .dcm files and nibabel for playing with nifti (.nii) files. 

## 2.1. Overview of SCANS and ASSESSORS (to facilitate future access) 
> ✅ (code)

At the beginning of execution, we will read the entire folder to create a JSON file containing folder information, including scans info (series UID,  of each folder) and segmentation info (segmentation name defined by the user, date of segmentation, and username of the segmentor for each segmentation folder). Defined in section 2.1. 

### 2.1.1 SCANS 
We loop through each SCANS folder to:
- read two random .dcm files (just to be sure and doubel check info, and in the case of error print the error in the json for that errorous object and add two values, if they are not similiar) and extrcact and sav:
    - the series folder path (full)
    - series number: (0020, 0011) Series Number
    - series UID: (0020, 0003) Series Instance UID
    - series description: (0008, 103E) Series description
    - class UID: (0008, 0016) SOP Class UID
    
This will be saved as json (for all folders in the SCANS) to faclitate finding the correct series for each, as well as providing the chance to review them manually, if needed.

### 2.1.1 ASSESSORS 
Then we will save this a json in the output folder under the same case folder name (for example 2072) with the name StudySeries_info.json

We loop through each ASSESSORS folder to:
- Find the segmentor name from XML (createdBy object in cat:entries)
- Find the segmentation was created (createdTime object inside cat:entries)
- Find the segmentation exported name from the .dcm file ((0008,103E) Series Description)
- Find the refrenced class SOP UID ((0008,1150) Referenced SOP Class UID) and refrenced series UID .dcm file.

Then we will save this a json in the output folder under the same case folder name (for example 2072) with the name Segmentations_info.json

## 2.2. **\[optional\] Select Validated Segmentations
> ✅ (code)

Ask the user if they want to select one segmentation (using the name defined by the segmentor or the name of the segmentation folder). This section doesn't have any guide, as it is clear. 

Optionally, the user can provide a path to an Excel file with a column for case number and a column for a list of segmentation names (this should be a list stored as a string or just one string value). 

## 2.3. Decoding the single segmentation.dcm
> ✅ (code)

#### Find the segment number for each slice

The first thing to read is the information of each slice we have in the .dcm file. We will use this to find the name of the object, the referenced segment number.

- (5200,9230) Per Frame Functional Groups Sequence
    - (0062,000B) Referenced Segment Number

CAUTION: There is something called referenced SOP instance UID in the per frame functional groups sequence. THIS IS NOT THE UID OF THE ORIGINAL SLICE OF THE CT SCAN OR MRI.

Hint: loop and create a list.

![alt text](images_of_readme/image-5.png)

#### Find the ImagePositionPatient (optional but highly recommended)

As I said earlier, I think image position patient would be usable in many scenarios of finding the corresponding slice in the series, and using this segmentation on different series (for example with more thin cuts, or with other contrast modalities).

- (5200,9230) Per Frame Functional Groups Sequence
    - (0020,0032) Image Position Patient

Hint: loop and create a list

![alt text](images_of_readme/image-6.png)

#### Find the segmentation number to segmentation object names

The DICOM has a section that describes the segmentation name mapping. It maps segmentation numbers (for example 10) to the names the person defines during segmentation (for example "pancreas"). When you want to start working with your files, you don't want to see "10" but you want to see "pancreas" so this is the first thing to understand. 

- The DICOM Element: (0062,0002) Segment Sequence 

Hint: loop and create a dictionary (1 --> P, which in my case refers to pancreas and the segmentor had known this)

![alt text](images_of_readme/image.png)

#### \[optional\] The recommended color for each segmentation object
This is the recommended color, which is the one the segmentor used during segmentation. Each segmented object has one of these things. 

- (0062,0002) Segment Sequence
    - (0062,000D) Recommended Display CIE Lab Value

Hint: append to the segmentation number to name dictionary

![alt text](images_of_readme/image-4.png)

#### Find segmentation mask pixel data (images): create a list

All segmentation mask data (pixels of mask image) is stored inside one object which is a list (the order of this list matches the order of the slices).

- (7FE0,0010) Pixel Data

Hint: this is already a list

![alt text](images_of_readme/image-2.png)

#### Find corresponding series in the original image: create a string

Each CT/MRI can have multiple series, and each series can have multiple slices. To find the corresponding series you should look for:

- (0008,1115) Referenced Series Sequence
    - {And inside this TAG look for} (0020,000E) Series Instance UID	

Hint: store as string

#### Find corresponding slice in the original image: create a tuple (list with an important order) 

- There is a list of objects that you can use to find the corresponding slice in the original image that segmentation was done on that slice. This is a list with the same length as the masks (in our example we had 9 masks, so we should have 9 objects for referenced UID)
    - The DICOM Element: (0008,1115) Referenced Series Sequence	

Hint: loop and create a list

![alt text](images_of_readme/image-1.png)

#### Name of segmentation defined by the segmentor

- Name of the segmentation file (the person who segmented the image saved (exported) this file with this name)
    - (0008,103E) Series Description

Hint: store as string

![alt text](images_of_readme/image-3.png)

#### \[optional but important\] Pixel spacing, slice thickness, space between slices, and Image Orientation Patient

Pixel spacing is really important and shows the distances of space. This shows the distance of pixels of our 2D image. If you want to 3D visualize your data, this is really important. So we will store this.

Space between slices shows the space distance between 2D slices to create the 3D object. We also saved slice thickness, but slice spacing is the thing you want to play with.

The image orientation patient will demonstrate the orientation of the image (e.g., axial and right to left or ...). It specifies the direction cosines of the first row and the first column with respect to the patient. This is important for 3D visualization of these masks.

![alt text](images_of_readme/image-8.png)

- (5200,9229) Shared Functional Groups sequence
    - (0020,0037) Image Orientation Patient
    - (0018,0050) Slice Thickness
    - (0018,0088) Spacing Between Slices
    - (0028,0030) Pixel Spacing

Hint: store as a dictionary of four lists with float values

![alt text](images_of_readme/image-7.png)

CAUTION: slice thickness is different than slice spacing, use slice spacing for your 3D visualization or ML usages.

#### \[optional\] If you want to search for the corresponding CT scan study
I don't know when you want to do this because XNAT saves each study inside one folder. But in any case that you want to do that:

- (0008,1150) Referenced SOP Class UID

Hint: store as string

#### \[optional\] Segmentation type (binary)

Just store this for your ML team. Binary means that when one mask is drawn, the previous mask will be removed, so each pixel can be assigned to just one segmentation object (or no object):

- (0062,0001) Segmentation Type

Hint: store as string

#### \[optional\] Frame column and row dimension

This is the dimension of each 2D slice (mask image).

- (0028,0010) Rows
- (0028,0011) Columns

Hint: store as dictionary with integer values

#### Finally

We will store all of the information, along with the specific information of each mask inside different pickles in a folder named Segmentations inside a folder with the same name as the case folder name (structure defined below) files as pickle files. 

2072
└───Segmentations
    ├───EN_verified_SN_sdamirsa_SEG_20240118_235251_213_S2
    │   └───P.pkl
    │   └───G.pkl
    └───EN_initialAAA_SN_sdamirsa_SEG_20241020_130224_332_S2
        └───P.pkl
        └───M.pkl
        └───MPD.pkl


## 2.4 - **Find corresponding series,  create original nifti, create segmentaion nifti**:
> ✅ (code)

This section will find the corresponding series in the SCANS folder and storing the original image data of that series as nifti.  Then, turns the previous segmentation pickle to nifti considering the original image slices (for each segmentation object separately). This will generate a segmentation nifti with a unified space (so both original and segmentation niftis would have a similar length/height). 

### 2.4.1. Find corresponding image series

Uses the previously prepared selected segmentations (PreparedSegmentations_info.json) and use ref_series_uid to find the corresponding folder using the study series info (StudySeries_info.json) using it's series_uid. Created an updated version of PreparedSegmentations_info with the corresponding series info (as a new dictionary of each selected segmentation) and save it as Ready2Nifti_info.json.

### 2.4.2. Create nifti of original CT/MRI images

It will uses Ready2Nifti_info.json to read all .dcm files in series_folder_path and then turn it into nifti file and sotre it in folder (in the same path of json) named Curated_Output. The name of the original CT is the name of the series number that you can understand from the series_folder_path (e.g. the series number of "/Users/as/Downloads/2072/SCANS/1/DICOM" is 1) and it will save it as 1.nii. If there is a previous 1.nii and the overwrite is off it will avoid doing this process again after checking the length of slices. 

### 2.4.3. Create nifti of segmentation object

It will uses Ready2Nifti_info to find each segmenation pickle and then, uses the pixel data, pixel spacing, slice spacing, and any other required information to create segmentation nifti files. The nifti file names is like this {refrenced series number}_ON_{object name}__FN_{name of segmentation folder} and if there is a previous nifti with the same length of each object we will avoid overwriting this. Also, consider the length of the nifti as this is a segmentaion of the original CT/MRI and it should have a same dimension. You should remmber the number of slices in the original image and then hanlde this issue by creating empty space for the slices of the original image that doesn't have segmentation. You should use refrenced_instance_UID to find the corresponding slices. You should also do this for each segmentaion object sepratly. 

## 2.5. \[Optional\] Merge (sum) multiple segmentation objects
> ✅ (code)

This will get a list of objects that it should concatenate. It will read the segmentaiton pickel in the PreparedSegmentations_info.json and add the 2D pixel arrays for any slice that has one or more than one objects defined in the input list of object names, and it will create a new object name, and it will update the counts and segment_name_count in the PreparedSegmentations_info. You should do the Stpe_2_4 again to have this object as .nii. 

---

<details>

<summary>To do</summary>

- [ ] Add 2.4. with NRRD support (and .seg.nrrd).
- [ ] Add the functionality to receive a dictionary of original series UID before uploading to XNAT and the XNAT (current) series UID or series number or folder name.

</details> 

---

*Contact*: You can reach me at sdamirsa@gmail.com for any suggestion to complete this repo. 



