"""
cs2star: Copy and convert a cryosparc dir into a relion dir
"""


import click


@click.command(context_settings=dict(help_option_names=['-h', '--help'], show_default=True))
@click.argument('job_dir', type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.argument('dest_dir', required=False, default='.', type=click.Path(file_okay=False))
@click.option('-f', '--overwrite', count=True, help='overwrite the existing destination directory if present.'
              'Passed once, overwrite star file only. Twice, also files/symlinks')
@click.option('-d', '--dry-run', is_flag=True,
              help='do not perform the command, simply check inputs and show what will be done.')
@click.option('-c/-s', '--copy/--symlink', default=False, help='copy the images or symlink to them')
@click.option('-m', '--micrographs', is_flag=True, help='copy/link the full micrographs')
@click.option('-p', '--patches', is_flag=True, help='copy/link the particle patches, if available')
@click.option('--sets', help='only use these sets (only used if job is Particle Sets Tool). Comma-separated list.')
@click.option('--classes', help='only use particles from these classes. Comma-separated list.')
@click.option('--swapxy/--no-swapxy', default=True, help='swap x and y axes')
@click.option('--inverty/--no-inverty', default=False, help='invert y axis')
@click.option('--invertx/--no-invertx', default=False, help='invert x axis')
def main(
    job_dir,
    dest_dir,
    overwrite,
    dry_run,
    copy,
    micrographs,
    patches,
    sets,
    classes,
    swapxy,
    inverty,
    invertx,
):
    """
    Copy and convert a cryosparc dir into a relion-ready dir.

    \b
    Parameters
    ==========
    JOB_DIR:
        a cryosparc job containing particles files.
    DEST_DIR:
        the destination directory. [default: '.']

    WARNING! This script will use --swapxy by default.
    This is because *usually* this is the convention change between
    cryosparc and relion. However, your mileage may vary, so you
    are encouraged to check you data after conversion.

    Note that if -p/-m are not passed, those columns are not
    usable (due to the mrc extension and broken path).
    """
    import sys
    import shutil
    from pathlib import Path
    import re

    import pandas as pd
    import numpy as np
    from rich.panel import Panel
    from inspect import cleandoc
    from rich.progress import Progress
    from rich import print
    try:
        import pyem
    except ModuleNotFoundError:
        print('You need to install pyem for cs2star to work: https://github.com/asarnow/pyem')

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
        if any(s in name for s in ('excluded', 'remainder', 'rejected', 'uncategorized')):
            continue
        if 'passthrough' in str(f):
            passthroughs.append(f)
        else:
            particles.append(f)
    if not particles:
        print('[red]No usable particle files were found')
        sys.exit(1)

    particles.sort()
    passthroughs.sort()
    # distinguish job types
    split_job = False
    if len(particles) != 1:
        if any('split_' in str(p) for p in particles):
            split_job = True
            # select sets
            if sets is not None:
                sets = [int(i) for i in sets.split(',')]
                filtered_particles = []
                filtered_passthroughs = []
                for prt, pst in zip(particles, passthroughs):
                    set_id = int(re.search('split_(\d+)', str(prt)).group(1))
                    if set_id in sets:
                        filtered_particles.append(prt)
                        filtered_passthroughs.append(pst)
                particles = filtered_particles
                passthroughs = filtered_passthroughs
        elif any(re.search('cryosparc_P\d+_J\d+_\d+_particles.cs', str(p)) for p in particles):
            particles = particles[-1:]

    dest_dir = Path(dest_dir)
    dest_star = dest_dir / 'particles.star'
    to_create = [dest_dir]
    if micrographs:
        dest_micrographs = dest_dir / 'micrographs'
        to_create.append(dest_micrographs)
    if patches:
        dest_patches = dest_dir / 'patches'
        to_create.append(dest_patches)

    log = cleandoc(f'''
        Particle files: {', '.join(str(f) for f in particles)}
        Passthrough files: {', '.join(str(f) for f in passthroughs)}
        Will create: {', '.join(str(f) for f in to_create + [dest_star])}
    ''')
    if dry_run:
        print(Panel(log))
        sys.exit()
    else:
        with open(dest_dir / 'cs2star.log', 'w+') as logfile:
            logfile.write(cleandoc(f'''
                # this directory was converted from cryosparc with cs2star.py. Command:'
                cs2star {" ".join(sys.argv[1:])}
            ''' + '\n'))
            logfile.write(log)

    # make dest dirs
    for d in to_create:
        d.mkdir(parents=True, exist_ok=True)
    if dest_star.is_file() and overwrite == 0:
        raise click.UsageError('particle file already exists. To overwrite, use -f')

    # convert positions
    passthroughs = [str(f) for f in passthroughs]
    if split_job:
        passthrough_files = [[p] for p in passthroughs]
    else:
        passthrough_files = [passthroughs for _ in particles]
    df = pd.DataFrame()

    with Progress() as progress:
        for f, p in progress.track(list(zip(particles, passthrough_files)), description='Loading particle data...'):
            data = np.load(f)
            df_part = pyem.metadata.parse_cryosparc_2_cs(
                data, passthroughs=p,
                minphic=0, boxsize=None, swapxy=swapxy, invertx=invertx, inverty=inverty)
            df = pd.concat([df, df_part], ignore_index=True)

        if classes is not None:
            classes = classes.split(',')
            print(f'selecting classes: {", ".join(classes)}')
            df = pyem.star.select_classes(df, classes)

        # clean up
        cleaning = progress.add_task('Cleaning up data...', total=2)
        df = pyem.star.check_defaults(df, inplace=True)
        progress.update(cleaning, advance=1)
        df = pyem.star.remove_deprecated_relion2(df, inplace=True)
        progress.update(cleaning, advance=1)

        # symlink/copy images
        def copy_images(paths, to_dir, label='micrographs', copy=False):
            exists = False
            for img in progress.track(paths, description=f'{"Copying" if copy else "Linking"} {label} to {to_dir}...'):
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
                print('[yellow]INFO: some files were not symlinked/copied because they already exist.\n'
                      'Use -ff to force overwrite.')

        def fix_path(path, new_parent):
            """
            replace the parent and add `s` at the end of a path
            """
            basename = Path(path).name
            return str(new_parent / basename) + 's'

        dest_dir = dest_dir.absolute()  # needed because relion thinks anything is relative to its "base" directory
        if micrographs:
            fix_mg_paths = progress.add_task('Fixing micrograph paths...', start=False)
            try:
                paths = np.unique(df['rlnMicrographName'].to_numpy())
            except KeyError:
                raise click.UsageError('could not find micrograph paths in the data.')
            # change them to the copied/symlinked version
            target_dir = dest_dir / 'micrographs'
            df['rlnMicrographName'] = df['rlnMicrographName'].apply(fix_path, new_parent=target_dir)
            progress.start_task(fix_mg_paths)
            progress.update(fix_mg_paths, completed=100)

            copy_images(paths, dest_micrographs, label='micrographs', copy=copy)
        if patches:
            for col in ('rlnImageName', 'ucsfImagePath'):
                if col in df.columns:
                    col_name = col
                    break
            else:
                raise click.UsageError('could not find patch paths in the data. Were the particles ever extracted?')
            fix_patch_paths = progress.add_task('Fixing micrograph paths...', start=False)
            progress.start_task(fix_patch_paths)
            paths = np.unique(df[col_name].to_numpy())
            # change them to the copied/symlinked version
            target_dir = dest_dir / 'patches'
            df[col_name] = df[col_name].apply(fix_path, new_parent=target_dir)
            progress.update(fix_patch_paths, completed=100)
            copy_images(paths, dest_patches, label='patches', copy=copy)

        writing = progress.add_task('Writing star file...', start=False)
        # write to file
        pyem.star.write_star(str(dest_star), df, resort_records=True, optics=True)
        progress.start_task(writing)
        progress.update(writing, completed=100)
