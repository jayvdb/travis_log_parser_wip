from __future__ import unicode_literals

import codecs
import os
import re
import sys


def split_slug(slug):
    """Return user and project."""
    parts = slug.rsplit('/', 1)
    assert '/' not in parts[1]
    return parts


def create_filename(slug, build_id, job_id, status):
    filename = '{0}/{1}.{2}-{3}.txt'.format(
        slug, build_id, job_id, status)
    return filename


def split_filename(filename):
    if not filename.endswith('.txt'):
        raise Exception('Unexpected filename {0}'.format(filename))

    filename = filename[:-4]
    job_id, status = filename.split('-', 1)
    build_id, job_number = job_id.split('.', 1)
    return {
        'build_id': int(build_id),
        'job_id': int(job_number),
        'status': status,
    }


def jobs(slug, build_id=None):
    files = os.listdir(slug)
    files = [filename for filename in files if filename.endswith('.txt')]

    if build_id:
        build_prefix = str(build_id) + '.'
        files = [filename for filename in files
                 if filename.startswith(build_prefix)]

    return [split_filename(filename) for filename in files]


def get_builds(slug):
    return set(job['build_id'] for job in jobs(slug))


def get_latest_build(slug):
    return max(get_builds(slug))


def parse_build_logs(slug, build_id):
    job_data = jobs(slug, build_id)

    job_ids = sorted(job['job_id'] for job in job_data)

    for job in job_data:
        filename = create_filename(
            slug, build_id, job['job_id'], job['status'])
        parse_job_file(filename)


def parse_job_file(filename):
    lines = codecs.open(filename, 'r', 'utf-8').read().splitlines()

    log_data = {}

    state = 0

    start = None
    clone_failed = False
    job_stopped = False
    job_stalled = False

    real_lines = []
    all_error_lines = []
    errors = {}
    error_id = None

    for line_no, line in enumerate(lines):

        if line.startswith('Build language: '):
            language = line[len('Build language: '):]
            if language != 'python':
                raise Exception('Unknown language: {0}'.format(language))
            log_data['language'] = language

        elif line.startswith('$ source ~/virtualenv/') and line.endswith('/bin/activate'):
            venv = line[len('$ source ~/virtualenv/'):-len('/bin/activate')]

            assert venv

            log_data['venv'] = venv
            state = 1

        elif 'The command "eval git submodule update" failed 3 times.' in line:
            clone_failed = True

        elif 'The command "eval git clone ' in line and 'failed 3 times.' in line:
            clone_failed = True

        elif 'The command "eval git checkout  ' in line and 'failed 3 times.' in line:
            clone_failed = True

        elif re.match('Ran (\d+) tests in (\d+.\d+)s', line):
            m = re.match('Ran (\d+) tests in (\d+.\d+)s', line)
            cnt = m.group(1)
            time = m.group(2)
            log_data['count'] = cnt
            log_data['time'] = time
            state = 1

        elif line.startswith('FAILED ('):
            results = line[len('FAILED ('):-1]
            results = dict(result.split('=') for result in results.split(', '))
            results = dict((name.lower(), cnt) for name, cnt in results.items())
            log_data['test_counts'] = results

        if line.startswith('========================================='):
            state = 2

        if state == 2:
            if line.startswith('ERROR: '):
                error_id = line[len('ERROR: '):]
                errors[error_id] = {'lines': []}
            elif line.startswith('FAIL: '):
                error_id = line[len('FAIL: '):]
                errors[error_id] = {'lines': []}
            elif line == '-------------------- >> begin captured logging << --------------------':
                if not error_id:
                    print('error_id is unexpectedly None while parsing:{0} {1}'.format(
                        line_no, line))
                state = 3
                errors[error_id]['logging'] = []

        if line == '--------------------- >> end captured logging << ---------------------':
            state = 2
            error_id = None

        if state == 1:
            real_lines.append(line)
        elif state > 1 and state < 5:
            all_error_lines.append(line)

        if error_id:
            if error_id not in errors:
                print('unexpected error_id ({0}) while parsing: {1}'.format(
                    error_id, line))
            if state == 2:
                #print(line)
                errors[error_id]['lines'].append(line)
            elif state == 3:
                errors[error_id]['logging'].append(line)

    log_data['state'] = state

    log_data['errors'] = errors

    assert log_data['language']

    log_data['lines'] = real_lines
    log_data['error_lines'] = all_error_lines

    if clone_failed:
        print('clone failed for {0}'.format(filename))
    elif job_stopped:
        print('job was stopped in {0}'.format(filename))
        print('Last lines were:')
        for line in log_data['lines'][-3:]:
            print(line)
    elif job_stalled:
        print('job was stalled in {0}'.format(filename))
        print('Last lines were:')
        for line in log_data['lines'][-3:]:
            print(line)
    elif 'venv' not in log_data:
        print('venv not found in {0}'.format(filename))
        print('Last lines were:')
        for line in log_data['lines'][-3:]:
            print(line)

    for error_id, error in log_data['errors'].items():
        print('==== {0} ===='.format(error_id))
        for line in error['lines']:
            print(line)
        print('')

    del log_data['errors']

    print('lines', len(real_lines))
    print('error lines', len(all_error_lines))
    del log_data['lines']
    del log_data['error_lines']
    print(log_data)


def main():
    """Main handler."""
    base_repo_slug = 'wikimedia/pywikibot-core'

    args = sys.argv[1:]

    if not args:
        print('no slug')
        sys.exit()

    if len(args) == 1 and os.path.isfile(args[0]):
        parse_job_file(args[0])
        return

    slug = args[0]

    if len(args) > 1:
        build_id = int(args[1])
    else:
        build_id = get_latest_build(slug)
    if len(args) > 2:
        job_id = int(args[2])
    else:
        job_id = None

    parse_build_logs(slug, build_id)


if __name__ == '__main__':
    main()
