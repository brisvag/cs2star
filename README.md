# cs2star.py

A simple utility that wraps around `csparc2star.py` to convert particle positions from Cryosparc JOB directories into a RELION-ready directory. On top of what `csparc2star.py` already does, this script automatically symlinks (or copies) the `.mrc` files, renaming them as appropriate to `mrcs` and updating the `rlnMicrographName` column to reflect the change.

# Usage

```bash
cs2star.py particle_positions_job_directory [destination_directory]
```

A couple more options are available, check out the help page with `-h`.
