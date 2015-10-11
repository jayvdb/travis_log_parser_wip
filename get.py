import datetime
import os
import sys

from github3 import login

import dateutil
import dateutil.parser

import requests

import travispy

_GITHUB_TOKEN = 'a0780aefab372178eddab588f7b3130a0cff5525'
_HEADERS = {'Accept': 'text/plain; version=2'}

# user = t.user()
# repos = t.repos(member=user.login)


def split_slug(slug):
    """Return user and project."""
    parts = slug.rsplit('/', 1)
    assert '/' not in parts[1]
    return parts


def split_extended_slug(slug):
    """Return user, project, build and job."""
    if not slug:
        return None, None, 0, 0

    parts = slug.rsplit('/')

    if len(parts) == 1:
        return parts[0], None, 0, 0
    elif len(parts) == 2:
        return parts[0], parts[1], 0, 0

    build_id, sep, job_id = parts[2].partition('.')
    build_id = int(build_id)
    if job_id:
        job_id = int(job_id)

    return parts[0], parts[1], build_id, job_id


def split_url_slug(url):
    _, _, path = url.partition('://travis-ci.org/')
    assert path
    path, _, line_no = path.partition('#')

    parts = path.split('/')

    if len(parts) == 2:
        return parts[0], parts[1], None, None

    if parts[2] == 'jobs':
        job_id = int(parts[3])
        return parts[0], parts[1], None, job_id
    elif parts[2] == 'builds':
        build_id = int(parts[3])
        return parts[0], parts[1], build_id, None


def download_job_log(job):
    filename = '{0}/{1}-{2}.txt'.format(job.repository.slug, job.number, job.state)
    if job.finished_at and os.path.exists(filename):
        file_ts = os.stat(filename).st_mtime
        file_ts = datetime.datetime.fromtimestamp(file_ts, dateutil.tz.tzutc())
        job_finish_ts = dateutil.parser.parse(job.finished_at)
        if file_ts >= job_finish_ts:
            return

    r = requests.get('https://api.travis-ci.org/jobs/%s/log' % job.id,
                     headers=_HEADERS)

    with open(filename, 'wb') as f:
        f.write(r.content)

    print('     wrote {0} with {1} chars'.format(filename, len(r.content)))


def download_logs(t, repo, build=None, job=None):
    print('downloading..', repo, build, job)
    assert repo
    if isinstance(repo, (str, unicode)):
        repo = t.repo(repo)

    if job and not build:
        jobs = t.jobs(slug=repo.slug, ids=job)
        assert len(jobs) == 1
        job = jobs[0]
        build = job.build

    if build:
        if isinstance(build, int):
            build = t.build(build)
            assert build.repository_id == repo.id
    else:
        build = t.build(repo.last_build_id)

    if job:
        if isinstance(job, int):
            for build_job in build.jobs:
                if build_job.number == job:
                    job = build_job
                    break

        jobs = [job]
    else:
        jobs = build.jobs

    for job in jobs:
        # TODO: enumerate all files starting with the job number,
        # and delete -started, -etc, when state is 'passed.
        print('   {0} - {1} - started at {2} (job id {3})'.format(job.number, job.state, job.started_at, job.id))
        download_job_log(job)


def download_repo_logs(t, repo, build=None):
    """Download the latest logs for a repo."""
    slug = repo.slug
    username, project = slug.rsplit('/', 1)

    assert '/' not in project
    if not os.path.exists(username):
        os.mkdir(username)
    if not os.path.exists(slug):
        os.mkdir(slug)

    print('{0} - {1} - {2}'.format(repo.slug, repo.description, repo.state))
    if not repo.last_build_id:
        print('  No builds')
        return

    if not build:
        try:
            build = t.build(repo.last_build_id)
        except travispy.errors.TravisError:
            print('  Failed to get builds')
            return

    # TODO: dont enumerate jobs if the files are all dated after the build end

    print('  Build {0} - {1} - ended {2} (duration: {3})'.format(build.number, build.state, build.finished_at, build.duration))
    for job in build.jobs:
        # TODO: enumerate all files starting with the job number,
        # and delete -started, -etc, when state is 'passed.
        print('   {0} - {1} - started at {2} (job id {3})'.format(job.number, job.state, job.started_at, job.id))
        download_job_log(job)


def get_forks(gh, slug):
    """Get fork slugs."""
    username, project = slug.rsplit('/', 1)
    repo = gh.repository(username, project)
    forks = repo.forks()

    return [fork.full_name for fork in forks]


def get_existing_travis_repos():
    """Get existing directory slugs."""
    # [3:] skip any leading .\\ or .//
    # TODO: make Win32 compliant
    paths = [root for root, dirs, files in os.walk('.')
             if '/' in root[3:]]
    # remove leading './'
    slugs = [path[2:] for path in paths]
    return slugs


def get_travis_repo(t, slug):
    """Return repo or None."""
    try:
        return t.repo(slug)
    except travispy.errors.TravisError:
        return None


def main():
    """Main handler."""
    base_repo_slug = 'wikimedia/pywikibot-core'

    t = travispy.TravisPy().github_auth(_GITHUB_TOKEN)

    args = sys.argv[1:]
    repos = []
    slugs = []
    user = project = build_id = job_id = None

    refresh = '--refresh' in args
    forks = '--forks' in args
    all_builds = '--all' in args
    build_count = 50

    args = [arg for arg in args if not arg.startswith('-')]

    if not args:
        user = t.user()
        repos = t.repos(member=user.login)
    elif refresh:
        slugs = get_existing_travis_repos()
    elif '://' in args[0]:
        user, project, build_id, job_id = split_url_slug(args[0])
        slug = slug = user + '/' + project
    else:
        slug = args[0]

        user, project, build_id, job_id = split_extended_slug(slug)
        slug = user + '/' + project

    if build_id or job_id:
        download_logs(t, slug, build_id, job_id)
        return

    repo = get_travis_repo(t, slug)
    if repo:
        repos.append(repo)
    else:
        print('warning: {0} does not have travis builds'.format(slug))

    if all_builds:
        builds = t.builds(slug=repo.slug)
        print('builds', len(builds))
        builds += t.builds(slug=repo.slug, after_number=builds[-1].number)
        for build in builds:
            if not hasattr(build, 'jobs'):
                assert hasattr(build, 'job_ids')
                print('ids', build.job_ids)
                # this doesnt work
                #build.jobs = t.jobs(ids=build.job_ids)
                build.jobs = [t.job(job_id) for job_id in build.job_ids]
                print(len(build.jobs))

            download_repo_logs(t, repo, build)
        return

    if forks:
        gh = login(token=_GITHUB_TOKEN)
        slugs = get_forks(gh, slug)

    if slugs:
        print('Checking: {0}'.format(slugs))

    for slug in slugs:
        repo = get_travis_repo(t, slug)
        if repo:
            print('{0} has travis builds enabled'.format(repo.slug))
            repos.append(repo)

    for repo in repos:
        download_repo_logs(t, repo)


if __name__ == '__main__':
    main()
