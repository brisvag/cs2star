# cs2star.py

A simple utility that wraps around `csparc2star.py` to convert particle positions from Cryosparc JOB directories into a RELION-ready directory. On top of what `csparc2star.py` already does, this script automatically symlinks (or copies) the `.mrc` files, renaming them as appropriate to `mrcs` and updating the `rlnMicrographName` column to reflect the change.

# Installation

This package requires [pyem](https://github.com/asarnow/pyem), which is not available on pip under that name. To install it manually:

```bash
git clone https://github.com/asarnow/pyem.git
cd pyem
pip install -e .
```

# Usage

```bash
cs2star cryosparc_job_dir [dest_dir]
```

A couple more options are available, check out the help page with `-h`.
