# Sources and licences of `data/raw/`

Facts live in `pipeline/env/fetch_data.sh` (URLs, pinned commits) and `data/raw/SHA256SUMS`
(checksums of every fetched file, paths relative to `data/raw/`). This note records
provenance and licence terms. Rajagopal files fetched 2026-10-29; Holzbaur and Mortensen
files fetched 2026-10-30. `fetch_data.sh --no-derive` downloads only what is absent and
verifies every checksum.

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

## Holzbaur 2005 Stanford-VA upper limb (arm)

| Item | Value |
|---|---|
| Model | Stanford VA Upper Limb Model, original: 50 muscles (OpenSim 3.0 file format, `Schutte1993Muscle`), 94 coordinates, 60 bodies; loads in OpenSim 4.6 |
| Paper | Holzbaur KRS, Murray WM, Delp SL (2005). A model of the upper extremity for simulating musculoskeletal surgery and analyzing neuromuscular control. Ann Biomed Eng 33(6):829-840. https://doi.org/10.1007/s10439-005-3320-7 |
| Fetched from (login-free) | https://github.com/mitkof6/OpenSimDatabase at commit `091168791bf007adb792c0c62488b57fff91de1a`, folder `upper_limb/complex/Stanford_VA_upper_limb/` (a mirror of the SimTK project https://simtk.org/projects/upper_limb) |
| Model URL | https://raw.githubusercontent.com/mitkof6/OpenSimDatabase/091168791bf007adb792c0c62488b57fff91de1a/upper_limb/complex/Stanford_VA_upper_limb/Stanford_VA_Upper_Limb_original.osim |
| Licence | BSD 3-Clause, Copyright (c) 2005, Stanford University and VA Palo Alto Health Care System. The mirror carries no licence file and the `.osim` embeds no notice, so the full text is reproduced below; it is the standard BSD 3-Clause wording with the copyright line above. Cite the paper when publishing results. |

| File (under `data/raw/holzbaur/`) | Upstream path (under `upper_limb/complex/Stanford_VA_upper_limb/`) | Notes |
|---|---|---|
| `Stanford_VA_Upper_Limb_original.osim` | same name | sha256 `02856ca4...9367b`; committed |
| `Geometry/*.vtp` (33 files) | `Geometry/` | Bone meshes the model names with `<geometry_file>`; git-ignored, re-fetched |

The upstream folder holds more files that stay unfetched: `NoTremor_Upper_Limb_v2..v7.osim` (simplified variants for a line-tracing task), `Stanford_VA_Upper_Limb.jnt` and `.msl` (older joint and muscle files), `GeometryAdditional/` and `bones/`.

BSD 3-Clause text:

> Copyright (c) 2005, Stanford University and VA Palo Alto Health Care System
> All rights reserved.
>
> Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
>
> 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
> 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
> 3. Neither the name of the copyright holders nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
>
> THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDERS OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## Mortensen 2018 HYOID 1.2 head and neck

| Item | Value |
|---|---|
| Model | HYOID 1.2 (scaled strength, updated inertia): 72 muscles (`Millard2012EquilibriumMuscle`), 30 coordinates, 15 bodies; OpenSim 4.4 file format; loads in OpenSim 4.6 |
| Project | SimTK "Musculoskeletal Model of Head and Neck Suitable for Dynamic Simulations", https://simtk.org/projects/neckdynamics |
| Paper | Mortensen J, Vasavada A, Merryweather A (2018). The inclusion of hyoid muscles improve moment generating capacity and dynamic simulations in musculoskeletal models of the head and neck. PLOS ONE. Citation as recorded in the upstream `notes.txt`. |
| Fetched from (login-free) | https://github.com/MyoHub/myoconverter at commit `cadf38059367a51239e6dc28c9fbe8b8fbd5149f`, folder `models/osim/Neck6D/` (the MyoConverter project's copy, downloaded from SimTK on 2023-01-12 and converted to OpenSim 4.4 format) |
| Model URL | https://raw.githubusercontent.com/MyoHub/myoconverter/cadf38059367a51239e6dc28c9fbe8b8fbd5149f/models/osim/Neck6D/HYOID_1.2_ScaledStrenght_UpdatedInertia.osim |
| Licence | MIT Use Agreement, "Copyright (c) 2018" (the upstream file names no holder): free use, copy, modify, merge, publish, distribute, sublicense and sell, provided the copyright and permission notice stay in all copies; software provided "as is" without warranty. The upstream `license` file is kept verbatim as `data/raw/mortensen/license`. Credits: Jonathan Mortensen, University of Utah, Department of Mechanical Engineering. |

| File (under `data/raw/mortensen/`) | Upstream path (under `models/osim/Neck6D/`) | Notes |
|---|---|---|
| `HYOID_1.2_ScaledStrenght_UpdatedInertia.osim` | same name | sha256 `40714669...f1469`; committed |
| `license` | `license` | sha256 `69e90eda...`; committed |
| `notes.txt` | `notes.txt` | Upstream provenance and credits; committed |
| `Geometry/*.vtp` (15 files) | `Geometry/` | Cervical vertebrae, skull, jaw, ribcage, clavicles, scapulae, thoracolumbar spine; git-ignored, re-fetched |

The upstream folder also holds `HYOID_1.2_ScaledStrenght_UpdatedInertia_adjusted.osim` (joint ranges rescaled for the MyoConverter pipeline) and `neck6d.osim`; both stay unfetched.

## Christophy 2012 lumbar model (trunk; manual download)

| Item | Value |
|---|---|
| Model | Lumbar_C_210, 210 to 238 muscles (OpenSim 2 file format; the OpenSim 4.6 load is untested) |
| Paper | Christophy M, Faruk Senan NA, Lotz JC, O'Reilly OM (2012). A musculoskeletal model for the lumbar spine. Biomech Model Mechanobiol 11(1-2):19-34. https://doi.org/10.1007/s10237-011-0290-6 |
| Source | SimTK group 567 on https://simtk.org (login needed) |
| Licence | MIT, University of California Berkeley 2010, per survey K19. Read the licence file in the download and add its text here once the file is in hand. |
| State | Awaiting the director's manual download. Place the files in `data/raw/christophy/` (see its `README.md`); `fetch_data.sh` skips with a message while the folder is empty, and `fetch_data.sh --record-christophy` pins their checksums in `SHA256SUMS`. `check_env.py` loads any `*.osim` there and reports the result. |

## Anatomy ontologies (not fetched yet)

| Source | URL | Licence as published |
|---|---|---|
| Uberon | http://purl.obolibrary.org/obo/uberon.owl (slim: `basic.owl`) | CC BY 3.0, http://creativecommons.org/licenses/by/3.0/ (OBO Foundry registry entry) |
| FMA | http://purl.obolibrary.org/obo/fma.owl; project http://si.washington.edu/projects/fma | OBO Foundry registry lists licence "CUSTOM" pointing to http://sig.biostr.washington.edu/projects/fm/FMA_Release, which offers a "Draft Open Source FMA License" (University of Washington Structural Informatics Group, 2006 draft). Read that text before redistributing any FMA subset. |
