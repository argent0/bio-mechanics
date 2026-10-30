# Sources and licences of `data/raw/`

Facts live in `pipeline/env/fetch_data.sh` (URLs, pinned commit) and `data/raw/SHA256SUMS`
(checksums of every fetched file, paths relative to `data/raw/rajagopal/`). This note records
provenance and licence terms. Files fetched 2026-10-29.

## Rajagopal full-body model and walking trial

| Item | Value |
|---|---|
| Project | SimTK "Full Body Model for use in Dynamic Simulations of Human Gait", https://simtk.org/projects/full_body |
| Paper | Rajagopal A, Dembia CL, DeMers MS, Delp DD, Hicks JL, Delp SL (2016). Full-body musculoskeletal model for muscle-driven simulation of human gait. IEEE Trans Biomed Eng. https://doi.org/10.1109/TBME.2016.2586891 |
| Fetched from (login-free) | https://github.com/opensim-org/opensim-models at commit `d9b05d470b1a481c222372c85b75772faf8f7792` (2025-11-05), a redistribution of the SimTK files; simtk.org downloads need a login and the site was unreachable from this machine |
| Licence | The SimTK project pages (read through web.archive.org, 2024 snapshot) attach the "MIT Use Agreement" (Copyright (c) 2015, Stanford University): free use, copy, modify, merge, publish, distribute, sublicense and sell, provided the copyright and permission notice stay in all copies; software provided "as is" without warranty. The `opensim-models` repository carries no separate licence file. Cite the paper when publishing results. |

| File (under `data/raw/rajagopal/`) | Upstream path | Notes |
|---|---|---|
| `Rajagopal2016.osim` | `Models/Rajagopal/Rajagopal2016.osim` | 80 muscles, 39 coordinates; OpenSim 4.5 format; muscle `fiber_damping` set to 0.1 upstream; committed |
| `README_upstream.txt` | `Models/Rajagopal/README.txt` | Upstream description of the model changes |
| `Geometry/*.vtp` (81 files) | `Geometry/` | Bone meshes the model names; git-ignored, re-fetched |
| `walk_pipeline/ExpData/motion_capture_walk.trc` | `Pipelines/Rajagopal/ExpData/` | Walking markers, 41 markers, 238 frames at 100 Hz (subject 11, no load); git-ignored |
| `walk_pipeline/ExpData/static_walk_1.trc`, `static_walk_2.trc` | same | Static poses for scaling and marker placement; git-ignored |
| `walk_pipeline/ExpData/grf_walk.mot` | same | Ground reaction forces, 2000 Hz, 0 to 2.3885 s; git-ignored |
| `walk_pipeline/ID/grf_walk.xml` | `Pipelines/Rajagopal/ID/` | External loads (right and left foot on `calcn_r`, `calcn_l`) |
| `walk_pipeline/Scale/*.xml`, `walk_pipeline/IK/ik_setup_walk.xml` | `Pipelines/Rajagopal/Scale/`, `IK/` | Upstream scale and inverse-kinematics setups |

Derived by `pipeline/env/make_trial.py` (OpenSim 4.6 `ScaleTool` twice, then `InverseKinematicsTool`):

| File | Content |
|---|---|
| `walk_pipeline/Scale/subject_scaled_walk.osim` | Scaled model for the subject, 80 muscles |
| `walk_pipeline/Scale/subject_scaled_walk_markerset.xml`, `scaleSet_applied_walk.xml`, `scale_output_walk.mot` | Scale-tool outputs |
| `walk_pipeline/IK/results_walk/ik_output_walk.mot` | Joint coordinates, 39 columns, 238 frames, 0 to 2.37 s; git-ignored |

The upstream pipeline also provides EMG (`emg_walk_raw.anc`, `emg_walk.mat`) for later validation of activations; it is not fetched yet.

## Anatomy ontologies (not fetched yet)

| Source | URL | Licence as published |
|---|---|---|
| Uberon | http://purl.obolibrary.org/obo/uberon.owl (slim: `basic.owl`) | CC BY 3.0, http://creativecommons.org/licenses/by/3.0/ (OBO Foundry registry entry) |
| FMA | http://purl.obolibrary.org/obo/fma.owl; project http://si.washington.edu/projects/fma | OBO Foundry registry lists licence "CUSTOM" pointing to http://sig.biostr.washington.edu/projects/fm/FMA_Release, which offers a "Draft Open Source FMA License" (University of Washington Structural Informatics Group, 2006 draft). Read that text before redistributing any FMA subset. |
