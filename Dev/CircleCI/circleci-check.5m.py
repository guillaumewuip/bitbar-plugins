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

def getWorstStatusFromWorfklows(workflows):
    if len(workflows) == 0:
        return None

    statusPriorities = [
        {
            'status': workflow.status,
            'priority': STATUS_PRIORITIES[workflow.status],
        }
        for workflow in workflows
    ]

    statusPriorities.sort(key = lambda s: s['priority'], reverse = True)

    return statusPriorities[0]['status']

def getLastWorkflow(workflows):
    if len(workflows) == 0:
        return None

    workflows.sort(key = lambda w: w.startDate, reverse = True)
    return workflows[0]

def isOlderThan(dateToCompare, maxDay):
    now = datetime.now()
    daysSinceDate = (now - dateToCompare).days

    return daysSinceDate > maxDay

def isBuildErrorWorkflow(name):
    return name == 'Build%20Error'

def getLastActivityDateFromBuilds(builds):
    dates = [ build['added-at'] for build in builds ]
    return datetime.strptime(dates[0], "%Y-%m-%dT%H:%M:%S.%fZ")

def getColor(status):
    return COLORS.get(status, '')

def getSymbol(status):
    return SYMBOLS.get(status, NO_SYMBOL)

def getBuildName(build):
    workflow = build.get('workflows')
    if workflow:
        return workflow.get('job_name')

    return '?'

def isBranchRunning(branch):
    return branch.status in ['running', 'retried']

def isBranchFailed(branch):
    return branch.status in ['failed', 'infrastructure_fail', 'timedout']

def isBranchCanceled(branch):
    return branch.status in ['canceled']

def getBranchLastSuccessDate(branch):
    if 'last_success' in branch:
        return datetime.strptime(branch['last_success']['pushed_at'], "%Y-%m-%dT%H:%M:%S.%fZ")

    return datetime.min

def getBranchLastNonSuccessDate(branch):
    if 'last_non_success' in branch:
        return datetime.strptime(branch['last_non_success']['pushed_at'], "%Y-%m-%dT%H:%M:%S.%fZ")

    return datetime.min

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
        return self.getJSON('projects', {
            'shallow': True,
            'branch_limit': 100,
        })

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

        branches = sorted(self.branches)

        for branch in branches:
            output.append(str(branch))

        return '\n'.join(output)

class Workflow:
    def __init__(self, id, name, status, startDate):
        self.id = id
        self.name = name
        self.status = status

        self.startDate = datetime.strptime(startDate, "%Y-%m-%dT%H:%M:%S.%fZ")

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
            workflow,
            details,
    ):
        self.project = project

        self.name = name
        self.status = status
        self.lastActivityDate = lastActivityDate
        self.usernames = usernames

        self.workflow = workflow
        self.details = details

    def getLink(self):
        BASE_URL = 'https://circleci.com/workflow-run/{}'

        if self.workflow:
            return BASE_URL.format(
                self.workflow.id,
            )

        return ''

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

    def shouldShowBranch(self, branchName, branchLastActivityDate, branchUsernames):
        isMaster = branchName == 'master'
        if self.config['alwaysShowMaster'] and isMaster:
            return True

        now = datetime.now()
        daysSinceBuild = (now - branchLastActivityDate).days

        if isOlderThan(branchLastActivityDate, self.config.get('maxDaySinceBuild')):
            return False

        usernames = self.config['usernamesFilter']
        hasUsernamesFilter = len(usernames) > 0
        isBranchFromFilteredUsernames = not hasUsernamesFilter or (
            bool(set(usernames) & set(branchUsernames))
        )

        return isBranchFromFilteredUsernames

    def computeStats(self):
        branches = [
            branch
            for project in self.projects
            for branch in project.branches
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
                name = unquote(branchName)

                workflows = []
                lastestWorkflows = branch.get('latest_workflows', [])

                for workflowName, workflow in lastestWorkflows.items():
                    workflows.append(Workflow(
                        workflow['id'],
                        workflowName,
                        workflow['status'],
                        workflow['created_at'],
                    ))

                builds = branch.get('recent_builds', []) + branch.get('running_builds', [])
                hasBuilds = len(builds) > 0

                if hasBuilds:
                    usernames = branch.get('pusher_logins', [])
                    lastActivityDate = getLastActivityDateFromBuilds(builds)

                    shouldShowBranch = self.shouldShowBranch(
                        name,
                        lastActivityDate,
                        usernames
                    )

                    if not shouldShowBranch:
                        continue

                    recentWorkflows = [
                        w for w in workflows
                        if not isOlderThan(w.startDate, self.config.get('maxDaySinceBuild'))
                        and not isBuildErrorWorkflow(w.name)
                    ]

                    if len(recentWorkflows) == 0:
                        continue

                    status = getWorstStatusFromWorfklows(recentWorkflows)

                    details = []

                    if status in NEED_DETAILS_STATUS: # not ok status
                        circleCIBuilds = self.ressource.getBuildsForBranch(
                            project.username,
                            project.reponame,
                            branchName,
                            self.config['branchDetailNumber'],
                        )

                        for build in circleCIBuilds:
                            buildName = getBuildName(build)
                            buildNumber = build.get('build_num')
                            buildStatus = build.get('status')

                            detail = BuildDetail(
                                project,
                                buildNumber,
                                buildName,
                                buildStatus,
                            )
                            details.append(detail)

                    lastWorkflow = getLastWorkflow(workflows)
                    branch = Branch(
                        project,
                        name,
                        status,
                        lastActivityDate,
                        usernames,
                        lastWorkflow,
                        details,
                    )

                    project.addBranch(branch)

            if len(project.branches) > 0:
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

