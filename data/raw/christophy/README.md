# Christophy 2012 lumbar model (manual download)

simtk.org group 567 ("A Musculoskeletal Model of the Lumbar Spine", Lumbar_C_210) needs a
login. Download the model archive in a browser, unpack it here (the `.osim` file and its
geometry), then run:

    pipeline/env/fetch_data.sh --no-derive --record-christophy

The command writes each file's sha256 to `data/raw/SHA256SUMS` (paths `./christophy/...`).
Later runs verify the files against those lines. `fetch_data.sh` skips files named `README*`.
