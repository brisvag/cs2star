#!/usr/bin/env python3
"""
copy and convert a cryosparc dir into a relion dir
"""

import argparse
import sys
from pathlib import Path
import shutil
import warnings

import pandas as pd
import numpy as np

try:
    import pyem
except ImportError:
    # better way to do this?
    pyem_path = '/programs/x86_64-linux/pyem/20200813/pyem'
    sys.path.append(pyem_path)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=SyntaxWarning)
        import pyem


def path(p):
    return Path(p).expanduser().resolve()


def parse():
    parser = argparse.ArgumentParser(prog='cs2star')
    parser.add_argument('positions', type=Path, help='a cryosparc job containing a "*particles.cs" file. The particles must contain references to images (blobs)')
    parser.add_argument('extraction', type=Path, help='a cryosparc "extract from micrographs" job directory')
    parser.add_argument('destination', nargs='?', default=Path.cwd(), type=Path, help='the destination directory')
    parser.add_argument('--classes', nargs='+', type=int, help='only use particles from these classes')
    parser.add_argument('-f', '--force-overwrite', action='count', help='overwrite the existing destination directory if present. Passed once, overwrite star file only. Twice, also files/symlinks')
    parser.add_argument('-d', '--dry-run', action='store_true', help='dry run')
    parser.add_argument('-c', '--copy', action='store_true', help='copy the images instead of symlinking to them')
    args = parser.parse_args(sys.argv[1:])
    return parser, args


def main():
    parser, args = parse()
    log = ['=' * 80, 'Parameters:']

    # interpret args
    # get all the particle files
    cs_pos = path(args.positions)
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
        parser.error('no usable particle positions files were found')
    log.append(f'Particle files: {[str(f) for f in cs_inputs]}')
    log.append(f'Passthrough files: {[str(f) for f in cs_passthroughs]}')

    cs_img = path(args.extraction) / 'extract'
    if not cs_img.is_dir():
        parser.error('the micrographs directory does not exist. Did you provide the right job?')
    log.append(f'Micrograph directory: {str(cs_img)}')

    dest = path(args.destination)
    dest_img = dest / 'images'
    dest_star = dest / 'particles.star'
    log_file = dest / 'cs2star.log'
    log.append(f'Destination directory: {str(dest)}')
    log.append('=' * 80)

    log = '\n'.join(log)
    print(log)

    # stop here on dry run
    if args.dry_run:
        sys.exit()

    # make dest dir
    dest_img.mkdir(parents=True, exist_ok=True)
    if dest_star.is_file() and args.force_overwrite == 0:
        parser.error('particle file already exists. To overwrite, use -f')

    # convert positions
    cs_passthroughs = [str(f) for f in cs_passthroughs]
    df_all = pd.DataFrame()
    for f in cs_inputs:
        print(f'Converting "{f.name}" to ".star" format...')
        data = np.load(f)
        df = pyem.metadata.parse_cryosparc_2_cs(data, passthroughs=cs_passthroughs,
                                                minphic=0, boxsize=None, swapxy=False)
        df_all.append(df, ignore_index=True)
    if args.classes is not None:
        print('Celecting classes...')
        df_all = pyem.star.select_classes(df_all, args.classes)

    print('Cleaning up data...')
    # clean up
    df_all = pyem.star.check_defaults(df_all, inplace=True)
    df_all = pyem.star.remove_deprecated_relion2(df_all, inplace=True)

    # fix micrograph paths
    df['rlnMicrographName'] = './images/' + df['rlnMicrographName'].str.split('/').str.get(-1) + 's'

    print('Writing star file...')
    # write to file
    pyem.star.write_star(str(dest_star), df, resort_records=True, optics=True)

    # symlink/copy images
    imgs_orig = cs_img.iterdir()
    imgs_dest = []
    exists = False
    print(f'{"Copying" if args.copy else "Linking"} images to "{dest_img}"...')
    for mrc in imgs_orig:
        # add s to extension for relion
        mrcs = Path(f'{mrc.relative_to(cs_img)}s')
        # save the relative path for later to edit the starfile
        imgs_dest.append(mrcs)
        moved = dest_img / mrcs
        if moved.is_file() and args.force_overwrite <= 1:
            exists = True
            continue
        else:
            if args.copy:
                shutil.copy(mrc, moved)
            else:
                if moved.is_symlink():
                    moved.unlink()
                moved.symlink_to(mrc)
    if exists and args.force_overwrite <= 1:
        print('INFO: some files were not symlinked/copied because they already exist. Use -ff to force overwrite')

    # write log
    header = '# this directory was converted from cryosparc with cs2star.py. Command:'
    command = " ".join(sys.argv)
    with open(log_file, 'w+') as f:
        f.write(f'{header}\n{command}\n{log}\n')

    print('Done!')

if __name__ == '__main__':
    main()
