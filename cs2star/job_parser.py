import json
import re
from pathlib import Path
import warnings


# copied from stemia.cryosparc.csplot

def update_dict(d1, d2):
    for k1, v in d1.items():
        for k2 in v:
            if not d1[k1][k2]:
                d1[k1][k2].update(d2[k1][k2])


def find_cs_files(job_dir, sets=None):
    """
    Recursively explore a job directory to find all the relevant cs files.

    This function recurses through all the parent jobs until it finds all the files
    required to have all the relevant info about the current job.
    """
    files = {
        'particles': {
            'cs': set(),
            'passthrough': set(),
        },
        'micrographs': {
            'cs': set(),
            'passthrough': set(),
        },
    }
    job_dir = Path(job_dir).absolute()
    try:
        with open(job_dir / 'job.json', 'r') as f:
            job = json.load(f)
    except FileNotFoundError:
        warnings.warn(f'parent job "{job_dir.name}" is missing or corrupted')
        return files

    j_type = job['type']
    for output in job['output_results']:
        metafiles = output['metafiles']
        passthrough = output['passthrough']
        k2 = 'passthrough' if passthrough else 'cs'
        if j_type == 'hetero_refine':
            # hetero refine is special because the "good" output is split into multiple files
            if (not passthrough and 'particles_class_' in output['group_name']) or (passthrough and output['group_name'] == 'particles_all_classes'):
                files['particles'][k2].add(job_dir.parent / metafiles[-1])
        elif j_type == 'particle_sets':
            if (matched := re.search(r'split_(\d+)', output['group_name'])) is not None:
                if sets is None or int(matched[1]) in [int(s) for s in sets]:
                    files['particles'][k2].add(job_dir.parent / metafiles[-1])
        else:
            # every remaining job type is covered by this generic loop
            for file in metafiles:
                if any(bad in file for bad in ('excluded', 'incomplete', 'remainder', 'rejected', 'uncategorized')):
                    continue
                if 'particles' in file:
                    k1 = 'particles'
                elif 'micrographs' in file:
                    k1 = 'micrographs'
                else:
                    continue

                files[k1][k2].add(job_dir.parent / file)

            for dct in files.values():
                for k in dct:
                    dct[k] = set(sorted(dct[k])[-1:])

    # remove non-existing files
    for dct in files.values():
        for kind, file_set in dct.items():
            for f in list(file_set):
                if not f.exists():
                    warnings.warn(
                        'the following file was supposed to contain relevant information, '
                        f'but does not exist:\n{f}'
                    )
                    file_set.remove(f)

    for parent in job['parents']:
        update_dict(files, find_cs_files(job_dir.parent / parent))
        if all(file_set for dct in files.values() for file_set in dct.values()):
            # found everything we need
            break

    return files
