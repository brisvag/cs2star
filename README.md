# cs2star

A simple utility that wraps around `csparc2star.py` to convert particle positions from Cryosparc JOB directories into a RELION-ready directory. On top of what `csparc2star.py` already does, this script will traverse the Cryosparc job tree to find the relevant `.cs` files, automatically symlinks (or copies) the `.mrc` files (renaming them as appropriate to `mrcs` and updating the `rlnMicrographName` column to reflect the change). `cs2star` also separates micrograph information in a `micrographs.star` file, which is required in several relion jobs.

# Installation

This package requires [pyem](https://github.com/asarnow/pyem), which is not available on pip under that name (there is a pyem on pip; that's a different package!). To install it manually [_NOTE: some fixes necessary for this are not yet on the main repo, so we're installing from a fork_]:

```bash
pip install git+https://github.com/brisvag/pyem.git
```

You can then install `cs2star` with pip:

```bash
pip install cs2star
```

# Usage

```bash
cs2star cryosparc_job_dir [dest_dir]
```

A couple more options are available, check out the help page with `-h`.

## Example

Assuming `Cryosparc/J23` is a classification job:

```bash
cs2star Cryosparc/J23 -p
```

will create in the working directory:
- a relion-ready `particles.star`
- a relion-ready `micrographs.star`
- a `patches` directory containing the particle images to be used by relion refinement
You can now run `relion` and provide `particles.star` and `micrographs.star` as the inputs.

## Tips

- While you can use the `--class` option to select specific classes from a cryosparc job, the class indexes do not correspond the the class order in Cryosparc (which is simply based on particle number). A much easier way to select specific classes to convert to `.star` is to use the `select 2D classes` job in cryosparc, then provide this job as input to cs2star.
- `--swapxy` defaults to `True`. This is because *usually* that's what you need; unfortunately, this may differ on a case by case basis, so make sure to check the data after conversion with you favourite viewer to ensure that particles are correctly centered.
