#!/usr/bin/env python3

"""
copy and convert a cryosparc dir into a relion dir
"""

import sys
import shutil
from pathlib import Path

import pandas as pd
import numpy as np
import click
import pyem


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('job_dir', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('dest_dir', required=False, default='.', type=click.Path(file_okay=False))
@click.option('-f', '--overwrite', count=True, help='overwrite the existing destination directory if present.'
              'Passed once, overwrite star file only. Twice, also files/symlinks')
@click.option('-d', '--dry-run', is_flag=True)
@click.option('-c/-s', '--copy/--symlink', help='copy the images or symlink to them [Default: copy]')
@click.option('-m', '--micrographs', is_flag=True, help='copy/link the full micrographs')
@click.option('-p', '--patches', is_flag=True, help='copy/link the particle patches, if available', show_default=True)
@click.option('--classes', help='only use particles from these classes. Comma-separated list.')
def main(job_dir, dest_dir, overwrite, dry_run, copy, micrographs, patches, classes):
    """
    Copy and convert a cryosparc dir into a relion-ready dir.

    JOB_DIR: a cryosparc job containing particles files.

    DEST_DIR: the destination directory. [Default: '.']
    """
    log = ['=' * 80]

    # get all the particle files
    job_dir = Path(job_dir)
    particles = []
    passthroughs = []
    for f in job_dir.iterdir():
        name = f.name
        if not name.endswith('.cs'):
            continue
        if 'particles' not in name and 'split_' not in name:
            continue
        if 'excluded' in name or 'remainder' in name:
            continue
        if 'passthrough' in str(f):
            passthroughs.append(f)
        else:
            particles.append(f)
    if not particles:
        click.UsageError('no usable particle positions files were found')

    particles.sort()
    passthroughs.sort()
    log.append(f'Particle files: {[str(f) for f in particles]}')
    log.append(f'Passthrough files: {[str(f) for f in passthroughs]}')

    dest_dir = Path(dest_dir)
    dest_star = dest_dir / 'particles.star'
    to_create = []
    if micrographs:
        dest_micrographs = dest_dir / 'micrographs'
        to_create.append(dest_micrographs)
    if patches:
        dest_patches = dest_dir / 'patches'
        to_create.append(dest_patches)
    log_file = dest_dir / 'cs2star.log'
    log.append(f'Will create: {[str(f) for f in [dest_star] + to_create]}')
    log.append('=' * 80)

    log = '\n'.join(log)
    click.secho(log, fg='green')

    # stop here on dry run
    if dry_run:
        sys.exit()

    # make dest dirs
    for d in to_create:
        d.mkdir(parents=True, exist_ok=True)
    if dest_star.is_file() and overwrite == 0:
        raise click.UsageError('particle file already exists. To overwrite, use -f')

    # convert positions
    passthroughs = [str(f) for f in passthroughs]
    df = pd.DataFrame()
    click.secho('Converting to star format...')
    for f in particles:
        data = np.load(f)
        df_part = pyem.metadata.parse_cryosparc_2_cs(data, passthroughs=passthroughs,
                                                     minphic=0, boxsize=None, swapxy=False)
        df = df.append(df_part, ignore_index=True)

    if classes is not None:
        classes = classes.split(',')
        click.secho('Selecting classes...')
        df = pyem.star.select_classes(df, classes)

    click.secho('Cleaning up data...')
    # clean up
    df = pyem.star.check_defaults(df, inplace=True)
    df = pyem.star.remove_deprecated_relion2(df, inplace=True)

    # symlink/copy images
    def copy_images(paths, to_dir, copy=False):
        exists = False
        with click.progressbar(paths, label=f'{"Copying" if copy else "Linking"} images to {to_dir}...') as images:
            for img in images:
                orig = job_dir.parent / img
                # new path + add s to extension for relion
                moved = Path(to_dir / (orig.name + 's'))
                if moved.is_file() and overwrite <= 1:
                    exists = True
                    continue
                else:
                    if moved.is_symlink():
                        moved.unlink()
                    if copy:
                        shutil.copy(orig, moved)
                    else:
                        moved.symlink_to(orig)
        if exists and overwrite <= 1:
            click.secho('INFO: some files were not symlinked/copied because they already exist.'
                        'Use -ff to force overwrite', bg='red')

    if micrographs:
        try:
            paths = np.unique(df['rlnMicrographName'].to_numpy())
        except KeyError:
            raise click.UsageError('could not find micrograph paths in the data.')
        # change them to the copied/symlinked version
        df['rlnMicrographName'] = './micrographs/' + df['rlnMicrographName'].str.split('/').str.get(-1) + 's'
        copy_images(paths, dest_micrographs, copy)
    if patches:
        for col in ('rlnImageName', 'ucsfImagePath'):
            if col in df.columns:
                col_name = col
                break
        else:
            raise click.UsageError('could not find patch paths in the data. Were the particles ever extracted?')
        paths = np.unique(df[col_name].to_numpy())
        # change them to the copied/symlinked version
        df[col_name] = './patches/' + df[col_name].str.split('/').str.get(-1) + 's'
        copy_images(paths, dest_patches, copy)

    click.secho('Writing star file...')
    # write to file
    pyem.star.write_star(str(dest_star), df, resort_records=True, optics=True)

    # write log
    header = '# this directory was converted from cryosparc with cs2star.py. Command:'
    command = " ".join(sys.argv)
    with open(log_file, 'w+') as f:
        f.write(f'{header}\n{command}\n{log}\n')

    click.secho('Done!')


if __name__ == '__main__':
    main()
