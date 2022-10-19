import json
import re
from pathlib import Path
import warnings


# simplified version from stemia.csplot
def find_cs_files(job_dir, sets=None):
    """
    Recursively explore a job directory to find all the relevant cs files.

    This function recurses through all the parent jobs until it finds all the files
    required to have all the relevant info about the current job.
    """
    files = {
        'cs': set(),
        'passthrough': set(),
    }
    try:
        job_dir = Path(job_dir)
        with open(job_dir / 'job.json', 'r') as f:
            job = json.load(f)
    except FileNotFoundError:
        warnings.warn(f'parent job "{job_dir.name}" is missing or corrupted')
        return files

    j_type = job['type']
    for output in job['output_results']:
        metafiles = output['metafiles']
        passthrough = output['passthrough']
        key = 'passthrough' if passthrough else 'cs'
        if j_type == 'hetero_refine':
            # hetero refine is special because the "good" output is split into multiple files
            if (not passthrough and 'particles_class_' in output['group_name']) or (passthrough and output['group_name'] == 'particles_all_classes'):
                files[key].add(job_dir.parent / metafiles[-1])
        elif j_type == 'particle_sets':
            if (matched := re.search(r'split_(\d+)', output['group_name'])) is not None:
                if sets is None or int(matched[1]) in [int(s) for s in sets]:
                    files[key].add(job_dir.parent / metafiles[-1])
        else:
            # every remaining job type is covered by this generic loop
            for file in metafiles:
                if any(bad in file for bad in ('excluded', 'incomplete', 'remainder', 'rejected', 'uncategorized')):
                    continue
                if 'particles' in file:
                    files[key].add(job_dir.parent / file)
                else:
                    continue

            for k in files:
                files[k] = set(sorted(files[k])[-1:])

    def update(d1, d2):
        for k in d1:
            if not d1[k]:
                d1[k].update(d2[k])

    for parent in job['parents']:
        update(files, find_cs_files(job_dir.parent / parent))
        if all(files.values()):
            break

    return files
