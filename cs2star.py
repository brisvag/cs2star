#!/usr/bin/env python3

"""
copy and convert a cryosparc dir into a relion dir
"""

import sys
import shutil
import warnings
from pathlib import Path

import pandas as pd
import numpy as np
import click

try:
    import pyem
except ImportError:
    # better way to do this?
    pyem_path = '/programs/x86_64-linux/pyem/20200813/pyem'
    sys.path.append(pyem_path)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=SyntaxWarning)
        import pyem

real_dir = click.Path(exists=True, file_okay=False, resolve_path=True)


@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.argument('positions', type=real_dir)
@click.argument('destination', required=False, default='.', type=click.Path(file_okay=False))
@click.option('--classes', help='only use particles from these classes. Comma-separated list.')
@click.option('-f', '--overwrite', count=True, help='overwrite the existing destination directory if present.'
              'Passed once, overwrite star file only. Twice, also files/symlinks')
@click.option('-d', '--dry-run', is_flag=True)
@click.option('-c/-s', '--copy/--symlink', help='copy the images or symlink to them')
def main(positions, destination, classes, overwrite, dry_run, copy):
    """
    Copy and convert a cryosparc dir into a relion-ready dir.

    POSITIONS: a cryosparc job containing a "*particles.cs" file.

    DESTINATION: the destination directory. [Default: '.']
    """
    log = ['=' * 80, 'Parameters:']

    # interpret args
    # get all the particle files
    cs_pos = Path(positions)
    cs_inputs = []
    cs_passthroughs = []
    for f in cs_pos.glob('*particles*.cs'):
        # discard excluded particles, if any
        if 'excluded' in str(f):
            continue
        # passthrough files
        elif 'passthrough' in str(f):
            cs_passthroughs.append(f)
        else:
            cs_inputs.append(f)
    if not cs_inputs:
        click.UsageError('no usable particle positions files were found')
    log.append(f'Particle files: {[str(f) for f in cs_inputs]}')
    log.append(f'Passthrough files: {[str(f) for f in cs_passthroughs]}')

    dest = Path(destination)
    dest_img = dest / 'images'
    dest_star = dest / 'particles.star'
    log_file = dest / 'cs2star.log'
    log.append(f'Destination directory: {str(dest)}')
    log.append('=' * 80)

    log = '\n'.join(log)
    click.secho(log, fg='green')

    # stop here on dry run
    if dry_run:
        sys.exit()

    # make dest dir
    dest_img.mkdir(parents=True, exist_ok=True)
    if dest_star.is_file() and overwrite == 0:
        click.UsageError('particle file already exists. To overwrite, use -f')

    # convert positions
    cs_passthroughs = [str(f) for f in cs_passthroughs]
    df_all = pd.DataFrame()
    with click.progressbar(cs_inputs, label='Converting to ".star" format') as bar:
        for f in bar:
            data = np.load(f)
            df = pyem.metadata.parse_cryosparc_2_cs(data, passthroughs=cs_passthroughs,
                                                    minphic=0, boxsize=None, swapxy=False)
            df_all.append(df, ignore_index=True)

    if classes is not None:
        classes = classes.split(',')
        click.secho('Selecting classes...')
        df_all = pyem.star.select_classes(df_all, classes)

    click.secho('Cleaning up data...')
    # clean up
    df_all = pyem.star.check_defaults(df_all, inplace=True)
    df_all = pyem.star.remove_deprecated_relion2(df_all, inplace=True)

    # get real micrograph paths
    imgs_orig = np.unique(df['rlnMicrographName'].to_numpy())
    # change them to the copied/symlinked version
    df['rlnMicrographName'] = './images/' + df['rlnMicrographName'].str.split('/').str.get(-1) + 's'

    click.secho('Writing star file...')
    # write to file
    pyem.star.write_star(str(dest_star), df, resort_records=True, optics=True)

    # symlink/copy images
    exists = False
    click.secho(f'{"Copying" if copy else "Linking"} images to "{dest_img}"...')
    for mrc in imgs_orig:
        orig = cs_pos.parent / mrc
        # new path + add s to extension for relion
        moved = Path(dest_img / (orig.name + 's'))
        if moved.is_file() and overwrite <= 1:
            exists = True
            continue
        else:
            if copy:
                shutil.copy(orig, moved)
            else:
                if moved.is_symlink():
                    moved.unlink()
                moved.symlink_to(orig)
    if exists and overwrite <= 1:
        click.secho('INFO: some files were not symlinked/copied because they already exist.'
                    'Use -ff to force overwrite', bg='red')

    # write log
    header = '# this directory was converted from cryosparc with cs2star.py. Command:'
    command = " ".join(sys.argv)
    with open(log_file, 'w+') as f:
        f.write(f'{header}\n{command}\n{log}\n')

    click.secho('Done!')


if __name__ == '__main__':
    main()
