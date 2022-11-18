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
@click.option('--sets', type=str, help='only use these sets (only used if job is Particle Sets Tool). Comma-separated list.')
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

    from .job_parser import find_cs_files

    sets = sets.split(',') if sets is not None else None
    # get all the particle files
    job_dir = Path(job_dir)
    job_files = find_cs_files(job_dir, sets=sets)

    particles = sorted(job_files['particles']['cs'])
    if not particles:
        print('[red]No usable particle files were found')
        sys.exit(1)

    particles_passthrough = sorted(job_files['particles']['passthrough'])
    micrographs = sorted(job_files['micrographs']['cs'])
    micrographs_passthrough = sorted(job_files['micrographs']['passthrough'])

    dest_dir = Path(dest_dir)
    dest_star = dest_dir / 'particles.star'
    dest_mic_star = dest_dir / 'micrographs.star'
    to_create = [dest_dir]
    if micrographs:
        dest_micrographs = dest_dir / 'micrographs'
        to_create.append(dest_micrographs)
    if patches:
        dest_patches = dest_dir / 'patches'
        to_create.append(dest_patches)

    log = cleandoc(f'''
        Particle files:
        {', '.join(str(f) for f in particles)}
        Particle Passthrough files:
        {', '.join(str(f) for f in particles_passthrough)}
        Micrograph files:
        {', '.join(str(f) for f in micrographs)}
        Micrograph Passthrough files:
        {', '.join(str(f) for f in micrographs_passthrough)}
        Will create: {', '.join(str(f) for f in to_create + [dest_star, dest_mic_star])}
    ''')
    if dry_run:
        print(Panel(log))
        sys.exit()
    else:
        with open(dest_dir / 'cs2star.log', 'w+') as logfile:
            logfile.write(cleandoc(f'''
                # this directory was converted from cryosparc with cs2star.py. Command:
                cs2star {" ".join(sys.argv[1:])}
            ''') + '\n')
            logfile.write(log)

    if len(particles) != len(particles_passthrough):
        if len(particles_passthrough) == 1:
            particles_passthrough = particles_passthrough * len(particles)
        else:
            raise ValueError('Number of passthrough files and particle files is incompatible')

    if len(micrographs) != len(micrographs_passthrough):
        if len(micrographs_passthrough) == 1:
            micrographs_passthrough = micrographs_passthrough * len(micrographs)
        else:
            raise ValueError('Number of passthrough files and particle files is incompatible')

    # make dest dirs
    for d in to_create:
        d.mkdir(parents=True, exist_ok=True)
    if dest_star.is_file() and overwrite == 0:
        raise click.UsageError('particle file already exists. To overwrite, use -f')
    if dest_star.is_file() and overwrite == 0:
        raise click.UsageError('micrographs file already exists. To overwrite, use -f')

    with Progress() as progress:

        df_part = pd.DataFrame()
        for f, p in progress.track(list(zip(particles, particles_passthrough)), description='Loading particle data...'):
            data = np.load(f)
            df_part_i = pyem.metadata.parse_cryosparc_2_cs(
                data, passthroughs=[p],
                minphic=0, boxsize=None, swapxy=swapxy, invertx=invertx, inverty=inverty)
            df_part = pd.concat([df_part, df_part_i], ignore_index=True)

        if classes is not None:
            classes = classes.split(',')
            print(f'selecting classes: {", ".join(classes)}')
            df_part = pyem.star.select_classes(df_part, classes)

        df_mic = pd.DataFrame()
        for f, p in progress.track(list(zip(micrographs, micrographs_passthrough)), description='Loading micrograph data...'):
            data = np.load(f)
            df_mic_i = pyem.metadata.parse_cryosparc_2_cs(
                data, passthroughs=[p],
                minphic=0, boxsize=None, swapxy=swapxy, invertx=invertx, inverty=inverty)
            df_mic = pd.concat([df_mic, df_mic_i], ignore_index=True)

        # clean up
        cleaning = progress.add_task('Cleaning up data...', total=2)
        df_part = pyem.star.check_defaults(df_part, inplace=True)
        progress.update(cleaning, advance=1)
        df_part = pyem.star.remove_deprecated_relion2(df_part, inplace=True)
        progress.update(cleaning, advance=1)

        # clean up
        cleaning = progress.add_task('Cleaning up data...', total=2)
        df_mic = pyem.star.check_defaults(df_mic, inplace=True)
        progress.update(cleaning, advance=1)
        df_mic = pyem.star.remove_deprecated_relion2(df_mic, inplace=True)
        progress.update(cleaning, advance=1)

        # symlink/copy images
        def copy_images(paths, to_dir, label='micrographs', copy=False, add_s=False):
            exists = False
            for img in progress.track(paths, description=f'{"Copying" if copy else "Linking"} {label} to {to_dir}...'):
                orig = job_dir.parent / img
                # new path + add s to extension for relion
                moved = Path(to_dir / (orig.name + ('s' if add_s else '')))
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

        def fix_path(path, new_parent, add_s=False):
            """
            replace the parent and add `s` at the end of a path
            """
            basename = Path(path).name
            return str(new_parent / basename) + ('s' if add_s else '')

        dest_dir = dest_dir.absolute()  # needed because relion thinks anything is relative to its "base" directory

        if micrographs:
            fix_mg_paths = progress.add_task('Fixing micrograph paths...', start=False)
            try:
                paths = np.unique(df_part['rlnMicrographName'].to_numpy())
            except KeyError:
                raise click.UsageError('could not find micrograph paths in the data.')
            # change them to the copied/symlinked version
            target_dir = dest_dir / 'micrographs'
            df_part['rlnMicrographName'] = df_part['rlnMicrographName'].apply(fix_path, new_parent=target_dir)
            progress.start_task(fix_mg_paths)
            progress.update(fix_mg_paths, completed=100)

            copy_images(paths, dest_micrographs, label='micrographs', copy=copy)
        if patches:
            for col in ('rlnImageName', 'ucsfImagePath'):
                if col in df_part.columns:
                    col_name = col
                    break
            else:
                raise click.UsageError('could not find patch paths in the data. Were the particles ever extracted?')
            fix_patch_paths = progress.add_task('Fixing micrograph paths...', start=False)
            progress.start_task(fix_patch_paths)
            paths = np.unique(df_part[col_name].to_numpy())
            # change them to the copied/symlinked version
            target_dir = dest_dir / 'patches'
            df_part[col_name] = df_part[col_name].apply(fix_path, new_parent=target_dir, add_s=True)
            progress.update(fix_patch_paths, completed=100)
            copy_images(paths, dest_patches, label='patches', copy=copy, add_s=True)

        writing = progress.add_task('Writing star files...', start=False, total=len(df_part.index) + len(df_mic.index))
        # write to file
        progress.start_task(writing)
        pyem.star.write_star(str(dest_star), df_part, resort_records=True, optics=True)
        progress.update(writing, advance=len(df_part.index))
        pyem.star.write_star(str(dest_mic_star), df_mic, resort_records=True, optics=True)
        progress.update(writing, advance=len(df_mic.index))
