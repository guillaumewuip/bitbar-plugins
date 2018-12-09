#!/usr/local/bin/python3

import os
from urllib.request import unquote
from datetime import datetime, timezone, timedelta
import base64
import pprint
import math

import requests
from dotenv import load_dotenv, find_dotenv

SYMBOLS = {
    'queued':               '⋯',
    'scheduled':            '⋯',
    'running':              '▶',
    'retried':              '▶',
    'success':              '✓',
    'fixed':                '✓',
    'failed':               '✗',
    'infrastructure_fail':  '✗',
    'timedout':             '⚠',
    'canceled':             '⊝',
    'not_running':          '⊝',
    'not_run':              '⊝',
    'no_tests':             ' ',
}

COLORS = {
    'queued':                '#AC7DD3',
    'scheduled':             '#AC7DD3',
    'running':               '#61D3E5',
    'retried':               '#61D3E5',
    'success':               '#39C988',
    'fixed':                 '#39C988',
    'failed':                '#EF5B58',
    'infrastructure_failed': '#EF5B58',
    'timedout':              '#F3BA61',
    'canceled':              '#898989',
    'not_running':           'black',
    'not_run':               'black',
    'no_tests':              'black',
}

NO_SYMBOL = '❂'

NEED_DETAILS_STATUS = [
    'running',
    'retried',
    'failed',
    'infrastructure_failed',
    'timeout',
]

STATUS_PRIORITIES = {
    'failed':               '5',
    'infrastructure_fail':  '5',
    'timedout':             '5',

    'queued':               '4',
    'scheduled':            '4',

    'running':              '3',
    'retried':              '3',

    'canceled':             '2',
    'not_running':          '2',
    'not_run':              '2',
    'no_tests':             '2',

    'success':              '1',
    'fixed':                '1',
}

# base64 16x16 png
CIRCLECI_LOGO = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAA40lEQVR4AaXTJVAFQRjA8Q+XhHtBIt5n0Ir1iCUSUkk4tEuQ6IO7Q8W9kUi4FFz++LLP397N727dV36e6KjoDwHIRy8OcYFTrKEVGfCB6BU/xKIHZ3jT4RVHqEMI/jUQj2G84s2FB3QgGCJ8gmDpveEMW9jHrZZ/j9qfBkpxpWX2IRfh+HiLMKON8ABpwmcQbwoLIRCEIgiCRCwq5Z7R8JFRheZvTUiCoAIrGEGOknavNDIh+kMiPt9NpWA/BCk4VtL3zBswnoL5Irq3jcXOttHZQdp25yB5c5TbEQzzy2R8nd8BRoTIylKntNIAAAAASUVORK5CYII='

pp = pprint.PrettyPrinter(indent=2)

def getStatusFromBuilds(builds):
    status = set([ build['status'] for build in builds ])
    return status

def getWorstStatus(status):
    statusPriorities = [
        { 'status': s, 'priority': STATUS_PRIORITIES[s] } for s in status
    ]

    statusPriorities.sort(key = lambda s: s['priority'], reverse = True)

    return statusPriorities[0]['status']

def getLastActivityDateFromBuilds(builds):
    dates = [ build['pushed_at'] for build in builds ]
    return datetime.strptime(dates[0], "%Y-%m-%dT%H:%M:%S.%fZ")

def getColor(status):
    return COLORS.get(status, '')

def getSymbol(status):
    return SYMBOLS.get(status, NO_SYMBOL)

def getBuildName(build):
    if 'workflows' in build:
        if 'workflow_name' in build['workflows']:
            return build['workflows']['workflow_name']

    return '?'

def isBranchRunning(branch):
    return branch.status in ['running', 'retried']

def isBranchFailed(branch):
    return branch.status in ['failed', 'infrastructure_fail', 'timedout']

def isBranchCanceled(branch):
    return branch.status in ['canceled']

class Ressource:
    def __init__(self, baseURL, apiToken):
        self.apiToken = apiToken
        self.baseURL = baseURL

    def getJSON(self, uri, queryParams = {}):
        queryParams.update({
            'circle-token': self.apiToken
        })
        url = self.baseURL + uri + '?'

        for queryParam, queryValue in queryParams.items():
            url += queryParam + '=' + str(queryValue) + '&'

        headers = { 'Accept': 'application/json' }

        r = requests.get(url, headers=headers)

        if not r.ok:
            raise RuntimeError('Can\‘t get ' + url)

        return r.json()

    def getProjects(self):
        return self.getJSON('projects')

    def getBuildsForBranch(self, username, reponame, branch, limit):
        uri = 'project/github/{}/{}/tree/{}'.format(
            username,
            reponame,
            branch,
        )
        return self.getJSON(uri, { 'limit': limit })

class Project:
    def __init__(self, check, username, reponame, repolink):
        self.check = check

        self.username = username
        self.reponame = reponame
        self.repolink = repolink

        self.branches = []

    def addBranch(self, branch):
        self.branches.append(branch)

    def __str__(self):
        output = []

        projectTitle = '{}/{} | href={}'.format(
            self.username,
            self.reponame,
            self.repolink
        )
        output.append(projectTitle)

        filterdBranches = [
            branch for branch in self.branches if self.check.shouldShowBranch(branch)
        ]
        branches = sorted(filterdBranches)

        for branch in branches:
            output.append(str(branch))

        return '\n'.join(output)

class BuildDetail:
    def __init__(self, project, buildNumber, buildName, status):
        self.project = project

        self.buildNumber = buildNumber
        self.buildName = buildName
        self.status = status

    def getLink(self):
        BASE_URL = 'https://circleci.com/gh/{}/{}/{}'
        return BASE_URL.format(
            self.project.username,
            self.project.reponame,
            self.buildNumber,
        )

    def __str__(self):
        link = self.getLink()
        color = getColor(self.status)
        symbol = getSymbol(self.status)

        buildTitle = '--{} {} | href={} color={}'.format(
            symbol,
            self.buildName,
            link,
            color
        )

        return buildTitle

class Branch:
    def __init__(
            self,
            project,
            name,
            status,
            lastActivityDate,
            usernames,
            details,
    ):
        self.project = project

        self.name = name
        self.status = status
        self.lastActivityDate = lastActivityDate
        self.usernames = usernames

        self.details = details

    def getLink(self):
        BASE_URL = 'https://circleci.com/gh/{}/{}/tree/{}'
        return BASE_URL.format(
            self.project.username,
            self.project.reponame,
            self.name,
        )

    def __lt__(self, otherBranch):
        if self.name == 'master': # always show master first
            return True
        if otherBranch.name == 'master':
            return False

        return self.lastActivityDate < otherBranch.lastActivityDate

    def __str__(self):
        output = []

        link = self.getLink();
        color = getColor(self.status)
        symbol = getSymbol(self.status)

        branchTitle = '{} {} | href={} color={}'.format(
            symbol,
            self.name,
            link,
            color
        )

        output.append(branchTitle)

        if self.details:
            for detail in self.details:
                output.append(str(detail))

        return '\n'.join(output)


class CircleCICheck:
    def __init__(self, config):
        self.config = config

        self.ressource = Ressource(config['apiEndpoint'], config['apiToken']);

        self.projects = []

        self.nbRunnigBranches = 0
        self.nbFailedBranches = 0
        self.nbCanceledBranches = 0

    def shouldShowBranch(self, branch):
        isMaster = branch.name == 'master'
        if config['alwaysShowMaster'] and isMaster:
            return True

        now = datetime.now()
        daysSinceBuild = (now - branch.lastActivityDate).days

        if (daysSinceBuild > config['maxDaySinceBuild']):
            return False

        usernames = config['usernamesFilter']
        hasUsernamesFilter = len(usernames) > 0
        isBranchFromFilteredUsernames = not hasUsernamesFilter or (
            bool(set(usernames) & set(branch.usernames))
        )

        return isBranchFromFilteredUsernames

    def computeStats(self):
        branches = [
            branch
            for project in self.projects
            for branch in project.branches
            if self.shouldShowBranch(branch)
        ]

        runningBranches = [
            branch for branch in branches if isBranchRunning(branch)
        ]

        failedBranches = [
            branch for branch in branches if isBranchFailed(branch)
        ]

        canceledBranches = [
            branch for branch in branches if isBranchCanceled(branch)
        ]

        self.nbRunnigBranches = len(runningBranches)
        self.nbFailedBranches = len(failedBranches)
        self.nbCanceledBranches = len(canceledBranches)

    def readProjects(self):
        circleCIProjects = self.ressource.getProjects()

        for circleCIProject in circleCIProjects:
            project = Project(
                self,
                circleCIProject['username'],
                circleCIProject['reponame'],
                circleCIProject['vcs_url']
            )

            circleCIBranches = circleCIProject['branches']
            for branchName, branch in circleCIBranches.items():
                recentBuilds = []
                runningBuilds = []
                hasRunningBuilds = False
                hasRecentBuilds = False

                if 'recent_builds' in branch:
                    recentBuilds = branch['recent_builds']
                    hasRecentBuilds = len(recentBuilds) > 0

                if 'running_builds' in branch:
                    runningBuilds = branch['running_builds']
                    hasRunningBuilds = len(runningBuilds) > 0

                if hasRunningBuilds or hasRecentBuilds:
                    usernames = branch['pusher_logins']

                    branchStatus = None
                    if hasRunningBuilds:
                        branchStatus = 'running'
                    else:
                        branchStatus = getWorstStatus(getStatusFromBuilds(recentBuilds))

                    lastActivityDate = getLastActivityDateFromBuilds(runningBuilds + recentBuilds)

                    details = []

                    if branchStatus in NEED_DETAILS_STATUS: # not ok status
                        circleCIBuilds = self.ressource.getBuildsForBranch(
                            project.username,
                            project.reponame,
                            branchName,
                            self.config['branchDetailNumber'],
                        )

                        for build in circleCIBuilds:
                            buildName = getBuildName(build)
                            buildNumber = build['build_num']
                            buildStatus = build['status']

                            detail = BuildDetail(
                                project,
                                buildNumber,
                                buildName,
                                buildStatus,
                            )
                            details.append(detail)

                    branch = Branch(
                        project,
                        unquote(branchName),
                        branchStatus,
                        lastActivityDate,
                        usernames,
                        details,
                    )

                    project.addBranch(branch)

            self.projects.append(project)

            self.computeStats()

    def __str__(self):
        output = []

        statusBarTitle = ''

        if self.nbRunnigBranches:
            statusBarTitle += str(self.nbRunnigBranches) + SYMBOLS['running'] + ' '

        if self.nbFailedBranches:
            statusBarTitle += str(self.nbFailedBranches) + SYMBOLS['failed'] + ' '

        if self.nbCanceledBranches:
            statusBarTitle += str(self.nbCanceledBranches) + SYMBOLS['canceled'] + ' '

        statusBarTitle += '| templateImage=' + CIRCLECI_LOGO
        output.append(statusBarTitle)

        output.append('---')

        for project in self.projects:
            output.append(str(project))
            output.append('---')

        return '\n'.join(output)


if __name__ == '__main__':
    load_dotenv(find_dotenv())

    config = {}

    # You need to set your CIRCLECI_API_TOKEN with an API Token from CircleCI.
    config['apiToken'] = os.getenv('CIRCLECI_API_TOKEN')
    if len(config['apiToken']) == 0:
        raise ValueError('CIRCLECI_API_TOKEN can not be empty')

    config['apiEndpoint'] = os.getenv('CIRCLECI_API_ENDPOINT') or 'https://circleci.com/api/v1.1/'

    # Comma-separated list of github logins to filter builds
    config['usernamesFilter'] = (os.getenv('CIRCLECI_USERNAMES_FILTER') or '').split(',')

    # 'false' to not always show master even if filterd master is filtered by CIRCLECI_USERNAMES_FILTER
    alwaysShowMaster = os.getenv('CIRCLECI_ALWAYS_SHOW_MASTER') # 'true' or 'false'
    config['alwaysShowMaster'] = not (alwaysShowMaster == 'false')

    # do not show branches without builds since CIRCLECI_MAX_DAYS_SINCE_BUILD days
    maxDaySinceBuild = os.getenv('CIRCLECI_MAX_DAYS_SINCE_BUILD')
    config['maxDaySinceBuild'] = int(maxDaySinceBuild) if maxDaySinceBuild else math.inf

    # show CIRCLECI_BRANCH_DETAIL_NUMBER jobs if branch is not ok
    branchDetailNumber = os.getenv('CIRCLECI_BRANCH_DETAIL_NUMBER')
    config['branchDetailNumber'] = int(branchDetailNumber) if branchDetailNumber else 10

    check = CircleCICheck(config)
    check.readProjects()

    print(check)

