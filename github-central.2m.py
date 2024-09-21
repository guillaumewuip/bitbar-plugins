#!/usr/bin/env python

# <xbar.title>Github</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <swiftbar.runInBash>false</swiftbar.runInBash

import os

from dotenv import load_dotenv, find_dotenv
from datetime import datetime
import json
import os
import sys
from urllib.request import Request, urlopen
from docopt import docopt
import pprint

load_dotenv(find_dotenv())

pp = pprint.PrettyPrinter(indent=2)

COLORS = {
    'inactive': '#333333',
    'mainText': '#111111',
    'alternativeText': '#111111',
}

help = '''github-central

Usage:
  github-central.py
  github-central.py <command> <param>

Options:
  -h --help          C'est généré automatiquement.
'''

MY_PRS_QUERY = '''{{
authorPrs: search(query: "type:pr state:open author:{login}", type: ISSUE, first: 100) {{
    edges {{
        node {{
            ... on PullRequest {{
                id
                number
                repository {{
                    nameWithOwner
                    defaultBranchRef{{
                        target{{
                            ...on Commit {{
                                status {{
                                    state
                                }}
                            }}
                        }}
                    }}
                }}
                author {{
                    login
                }}
                createdAt
                url
                title
                state
                isDraft
                commits(last: 1) {{
                    nodes {{
                        commit {{
                            statusCheckRollup {{
                              state
                            }}
                            checkSuites(last: 10) {{
                                nodes {{
                                    app {{
                                        name
                                    }},
                                    conclusion,
                                    status,
                                    url,
                                    checkRuns(last: 100) {{
                                        nodes {{
                                            name,
                                            detailsUrl,
                                            status,
                                            conclusion
                                        }}
                                    }}
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }}
    }}
}}
assigneePrs: search(query: "type:pr state:open assignee:{login}", type: ISSUE, first: 100) {{
    edges {{
        node {{
            ... on PullRequest {{
                id
                number
                repository {{
                    nameWithOwner
                    defaultBranchRef{{
                        target{{
                            ...on Commit {{
                                status {{
                                    state
                                }}
                            }}
                        }}
                    }}
                }}
                author {{
                    login
                }}
                createdAt
                url
                title
                state
                isDraft
                headRefName
                commits(last: 1) {{
                    nodes {{
                        commit {{
                            statusCheckRollup {{
                              state
                            }}
                            checkSuites(last: 100) {{
                                nodes {{
                                    checkRuns(last: 10) {{
                                        nodes {{
                                            name,
                                            detailsUrl,
                                            status,
                                            conclusion
                                        }}
                                    }}
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }}
    }}
}}
}}'''

REPOS_QUERY = '''{{
repositories: search(query: "{query}", type: REPOSITORY, first: {repositoryNumber}) {{
    edges {{
        node {{
          ... on Repository {{
                name
                url
                releases(first: {limitReleases}, orderBy: {{ direction: DESC, field: CREATED_AT }}) {{
                    edges {{
                        node {{
                            tagName
                            name
                            author {{
                                login
                                name
                            }}
                            url
                        }}
                    }}
                }}
            }}
        }}
    }}
}}
}}'''

NOTIFICATIONS_REASON_TO_EMOJIS = {
    'assign': '👨‍💻',
    'author': '👨‍💻',
    'comment': '💬',
    'invitation': '🎉',
    'manual': '👀',
    'mention': '💬',
    'team_mention': '💬',
    'state_change': '🔁',
    'subscribed': '👀',
    'review_requested': '🔍',
}

NOTIFICATIONS_TYPE_TO_ISSUE_PR = {
    'Issue': 'issues',
    'PullRequest': 'pull',
}

CHECK_STATE_EMOJIS = {
    'RUNNING': '⚙️',
    'PENDING': '⚙️',
    'ACTION_REQUIRED': '❌',
    'CANCELLED': '✖️',
    'SKIPPED': '✖️',
    'FAILURE': '❌',
    'NEUTRAL': '✅',
    'SUCCESS': '✅',
    'TIMED_OUT': '❌',
}

def getPrStateEmoji(isDraft, state):
    emoji1 = CHECK_STATE_EMOJIS[state] if state else CHECK_STATE_EMOJIS['RUNNING']
    emoji2 = '📝' if isDraft else ''

    return emoji1 + ' ' + emoji2

def strToDate(dateStr):
    return datetime.strptime(dateStr, '%Y-%m-%dT%H:%M:%SZ')


class PullRequests:
    def __init__(self, config):
        self.config = config

        self.prs = {};

        self.counts = {
            'totalPrs': 0,
            'errorPrs': 0,
        }

    def savePr(self, repositoryName, prId, pr):
        if not repositoryName in self.prs:
            self.prs[repositoryName] = {
                'state': pr.get('baseBranchState'),
                'prs': {},
            }

        if not prId in self.prs[repositoryName]['prs']:
            self.prs[repositoryName]['prs'][prId] = pr

        self.counts['totalPrs'] += 1

        state = pr.get('checkSuites').get('state')
        if state and not state == 'SUCCESS' and not state == 'PENDING' and not state == 'RUNNING' and not state == 'NEUTRAL':
            self.counts['errorPrs'] += 1

    def readCheckSuites(self, lastCommit):
        if not lastCommit:
            return {
                'runs': [],
                'state': None,
            }
        else:
            status = lastCommit.get('commit').get('statusCheckRollup')
            result = {
                'runs': [],
                'state': 'PENDING' if not status else status.get('state')
            }

            checkSuitesData = lastCommit.get('commit').get('checkSuites').get('nodes')

            for checkSuiteData in checkSuitesData:
                runsData = checkSuiteData.get('checkRuns').get('nodes')

                for runData in runsData:
                    status = runData.get('status')
                    conclusion = runData.get('conclusion')

                    state = 'RUNNING' if not (status == 'COMPLETED') else conclusion

                    run = {
                        'state': state,
                        'name': runData.get('name'),
                        'url': runData.get('detailsUrl'),
                    }

                    result['runs'] += [run]

            return result

    def readResponse(self, prsResponse):
        for node in prsResponse:
            nodeData = node.get('node')

            checkSuites = self.readCheckSuites(nodeData.get('commits').get('nodes')[0])

            pr = {
                'id': nodeData.get('id'),
                'number': nodeData.get('number'),
                'title': nodeData.get('title'),
                'createdAt': nodeData.get('createdAt'),
                'author': nodeData.get('author').get('login'),
                'mergeStateStatus': nodeData.get('mergeStateStatus'),
                'url': nodeData.get('url'),
                'state': nodeData.get('state'),
                'isDraft': nodeData.get('isDraft'),
                'branch': nodeData.get('headRefName'),
                'checkSuites': checkSuites,
                'baseBranchState': nodeData.get('repository').get('defaultBranchRef').get('target').get('status')
            }

            if pr.get('state') != 'OPEN':
                continue

            repositoryName = nodeData.get('repository').get('nameWithOwner')

            if repositoryName not in self.config['GITHUB_HIDDEN_PRS_REPOS']:
                self.savePr(repositoryName, pr.get('id'), pr);

    def sort(self):
        for repositoryName in self.prs:
            state = self.prs[repositoryName]['state']
            prs = self.prs[repositoryName]['prs']

            listPrs = sorted(
                prs.values(),
                key=lambda pr: pr.get('createdAt'),
                reverse=True
            )

            lastActivityDate = listPrs[0].get('createdAt')


            self.prs[repositoryName] = {
                'repositoryName': repositoryName,
                'prs': listPrs,
                'state': state,
                'lastActivityDate': lastActivityDate
            }

        self.prs = sorted(
            self.prs.values(),
            key=lambda repo: repo['lastActivityDate'],
            reverse=True
        )

    def request(self, query):
        headers = {
            'Authorization': 'bearer ' + self.config['GITHUB_ACCESS_TOKEN'],
            'Content-Type': 'application/json',
            'Accept': 'application/vnd.github.merge-info-preview+json,application/vnd.github.shadow-cat-preview,application/vnd.github.antiope-preview+json',
        }
        data = json.dumps({'query': query}).encode('utf-8')

        req = Request(
            'https://api.github.com/graphql',
            data=data,
            headers=headers,
        )

        body = urlopen(req).read()
        return json.loads(body)

    def get(self):
        login = self.config['GITHUB_LOGIN']

        queryBody = MY_PRS_QUERY.format(login=login)

        response = self.request(queryBody)

        authorPrs = response.get('data').get('assigneePrs').get('edges', [])
        assigneePrs = response.get('data').get('assigneePrs').get('edges', [])

        prs = authorPrs + assigneePrs
        uniquePrs = list({pr.get('node').get('id'):pr for pr in prs}.values())

        self.readResponse(uniquePrs)

        self.sort()

    def getEmoji(self, pr):
        isDraft = pr.get('isDraft')
        state = pr.get('checkSuites').get('state')

        return getPrStateEmoji(isDraft, state)

    def __str__(self):
        output = []

        if not self.prs:
            output.append('No pull-request| color={}'.format(COLORS['inactive']));
        else:
            output.append('Pull requests| color={}'.format(COLORS['alternativeText']))
            for repo in self.prs:
                defaultBranchStateEmoji = CHECK_STATE_EMOJIS[repo.get('state').get('state')] if repo.get('state') else CHECK_STATE_EMOJIS['NEUTRAL']
                output.append('{} - {} |href={} color={}'.format(
                    repo['repositoryName'],
                    defaultBranchStateEmoji,
                    'https://github.com/{}/pulls'.format(repo['repositoryName']),
                    COLORS['alternativeText'],
                ))

                prs = repo['prs']

                for pr in prs:
                    output.append('{} #{} {} | href={} color={}'.format(
                        self.getEmoji(pr),
                        pr.get('number'),
                        pr.get('title').replace('|', '-'),
                        pr.get('url'),
                        COLORS['mainText']
                    ))

                    output.append('--{} | color={} terminal=false bash="/bin/bash" param1="-c" param2="echo -n {} | pbcopy"'.format(
                        pr.get('branch'),
                        COLORS['mainText'],
                        pr.get('branch'),
                    ))

                    output.append('-- --- | color={}'.format(COLORS['inactive']))

                    runs = pr.get('checkSuites').get('runs')

                    for run in runs:
                        output.append('--{} {} | href={} color={}'.format(
                            CHECK_STATE_EMOJIS[run.get('state')],
                            run.get('name').replace('|', '-'),
                            run.get('url').replace('|', '-'),
                            COLORS['mainText']
                        ))

        return '\n'.join(output)

class Notifications:
    def __init__(self, config):
        self.config = config

        self.notifications = {}
        self.repositoryLastActivityDates = {}
        self.nbNotifications = 0

    def request(self):
        headers = {
            'Authorization': 'bearer ' + self.config['GITHUB_ACCESS_TOKEN'],
            'Content-Type': 'application/json',
        }
        req = Request(
            'https://api.github.com/notifications',
            headers=headers,
        )
        body = urlopen(req).read()
        return json.loads(body)

    def save(self, repositoryName, notification):
        if not repositoryName in self.notifications:
            self.notifications[repositoryName] = []

        self.notifications[repositoryName].append(notification)
        self.nbNotifications += 1

    def sort(self):
        for repositoryName in self.notifications:
            notifications = self.notifications[repositoryName]
            self.notifications[repositoryName] = sorted(
                notifications,
                key=lambda notification: notification['lastActivityDate'],
                reverse=True
            )

            self.repositoryLastActivityDates[repositoryName] = max(
                self.notifications[repositoryName],
                key=lambda notification: notification['lastActivityDate'],
            )

        self.repositoryLastActivityDates = sorted(
            self.repositoryLastActivityDates.items(),
            key=lambda x: x[1]['lastActivityDate'],
            reverse=True,
        )

    def get(self):
        response = self.request()

        for notification in response:
            threadId = notification.get('id')
            lastActivityDate = notification.get('updated_at')
            reason = notification.get('reason')

            title = notification.get('subject').get('title')
            url = notification.get('subject').get('url')
            notificationType = notification.get('subject').get('type')

            repositoryName = notification.get('repository').get('full_name')

            self.save(repositoryName, {
                'threadId': threadId,
                'lastActivityDate': strToDate(lastActivityDate),
                'reason': reason,
                'title': title,
                'url': url,
                'type': notificationType,
                'repositoryName': repositoryName,
            });

        self.sort()

    def getReasonEmoji(self, notification):
        return NOTIFICATIONS_REASON_TO_EMOJIS.get(
            notification.get('reason'),
            '?',
        )

    def getLink(self, notification):
        url = notification.get('url')
        if not url:
            return 'https://github.com/notifications'

        urlParts = notification.get('url').split('/')
        prOrIssueId = urlParts[-1]

        thing = NOTIFICATIONS_TYPE_TO_ISSUE_PR.get(
            notification.get('type')
        )

        if not thing:
            return 'https://github.com/notifications'

        return 'https://github.com/{}/{}/{}'.format(
            notification['repositoryName'],
            thing,
            prOrIssueId,
        )

    def getMarkReadCommand(self, notification):
        scriptPath = os.path.realpath(__file__)

        return (
            scriptPath,
            'read-notification',
            notification.get('threadId'),
        )

    def __str__(self):
        output = []

        notificationsLink = 'http://github.com/notifications'

        if not self.nbNotifications:
            output.append('No notification | color={} href={}'.format(
                COLORS['inactive'],
                notificationsLink,
            ))
        else:
            output.append('{} notifications | color={} href={}'.format(
                self.nbNotifications,
                COLORS['alternativeText'],
                notificationsLink,
            ))

        for repositoryName, _ in self.repositoryLastActivityDates:
            output.append('-- {}'.format(repositoryName))

            notifications = self.notifications[repositoryName]

            for notification in notifications:
                output.append('--{} {} | href={} color={}'.format(
                    self.getReasonEmoji(notification),
                    notification['title'].replace('|', '-'),
                    self.getLink(notification),
                    COLORS['mainText'],
                ))

        return '\n'.join(output)

    def readNotification(self, notificationId):
        headers = {
            'Authorization': 'bearer ' + self.config['GITHUB_ACCESS_TOKEN'],
        }
        url = 'https://api.github.com/notifications/threads/{}'.format(notificationId)

        req = Request(
            url,
            headers=headers,
        )
        req.get_method = lambda: 'PATCH'

        body =  urlopen(req).read()

class Releases:
    def __init__(self, config):
        self.config = config
        self.repos = config['GITHUB_RELEASES_REPOS']
        self.numberOfReleases = config['GITHUB_RELEASES_NUMBER']

    def request(self, query):
        headers = {
            'Authorization': 'bearer ' + self.config['GITHUB_ACCESS_TOKEN'],
            'Content-Type': 'application/json',
            'Accept': 'application/vnd.github.merge-info-preview+json',
        }
        data = json.dumps({'query': query}).encode('utf-8')

        req = Request(
            'https://api.github.com/graphql',
            data=data,
            headers=headers,
        )

        body = urlopen(req).read()
        return json.loads(body)

    def get(self):
        query = ' '.join([ 'repo:' + repo for repo in self.repos ])
        queryBody = REPOS_QUERY.format(
            query=query,
            limitReleases=self.numberOfReleases,
            repositoryNumber=len(self.repos),
        )

        response = self.request(queryBody)

        self.repositories = response.get('data').get('repositories')

    def __str__(self):
        output = []

        output.append('Releases')

        repositories = self.repositories.get('edges', [])

        for repository in repositories:
            repoData = repository.get('node')

            output.append('{} | href={} color={}'.format(
                repoData.get('name').replace('|', '-'),
                repoData.get('url') + '/releases',
                COLORS['mainText'],
            ))

            releases = repoData.get('releases').get('edges', [])

            for release in releases:
                releaseData = release.get('node')

                if not releaseData:
                    continue

                output.append('--{} ({}) | href={} color={}'.format(
                    releaseData.get('tagName'),
                    releaseData.get('author', {}).get('login'),
                    releaseData.get('url'),
                    COLORS['mainText'],
                ))

        return '\n'.join(output)

if __name__ == '__main__':
    config = {}
    config['GITHUB_ACCESS_TOKEN'] = os.getenv('GITHUB_ACCESS_TOKEN')
    config['GITHUB_LOGIN'] = os.getenv('GITHUB_LOGIN')

    config['GITHUB_RELEASES_REPOS'] = os.getenv('GITHUB_RELEASES_REPOS').split(',') if os.getenv('GITHUB_RELEASES_REPOS') else []

    config['GITHUB_RELEASES_NUMBER'] = 10

    config['GITHUB_HIDDEN_PRS_REPOS'] = os.getenv('GITHUB_HIDDEN_PRS_REPOS').split(',') if os.getenv('GITHUB_HIDDEN_PRS_REPOS') else []

    args = docopt(help)

    notifications = Notifications(config)
    releases = Releases(config)
    pullRequests = PullRequests(config)

    pullRequests.get()
    if args['<command>'] == 'read-notification':
        notifications.readNotification(args['<param>'])

    notifications.get()
    notificationsTitle = '{}⚑'.format(notifications.nbNotifications) if notifications.nbNotifications else ''

    releases.get()

    pullRequestsTitle = '{}✗/{}'.format(pullRequests.counts['errorPrs'], pullRequests.counts['totalPrs'])

    print(':tray.and.arrow.down.fill: {} {} | color={} size=11'.format(
        notificationsTitle,
        pullRequestsTitle,
        COLORS['mainText'],
    ))
    print('---')
    print(str(notifications))
    print('---')
    print(str(releases))
    print('---')
    print(str(pullRequests))

