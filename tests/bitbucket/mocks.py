
import json
from zuul.driver.bitbucket.bitbucketconnection import BitbucketConnection
from test.base import BaseTestCase


class CommonConnectionTest(BaseTestCase):
    realProject = 'sys-ic/foobar'
    realGitUrl = 'ssh://git@bitbucket.glumfun.tests:59/sys-ic/foobar.git'
    realWebUrl =\
        'https://bitbucket.glumfun.tests/projects/SYS-IC/repos/foobar/browse'

    def _connection(self):
        con = BitbucketConnection(None, 'tester',
                                  {'server': 'bitbucket.glumfungl.tests',
                                   'server_git_port': 59,
                                   'server_rest_port': 43,
                                   'server_user': 'mark',
                                   'server_pass': 'foobar'})
        return con


class BitbucketClientMock():
    def __init__(self, server, port):
        self.server = server
        self.port = port

    def setCredentials(self, user, pw):
        self.user = user
        self.pw = pw

    def get(self, path):
        if path == '/rest/api/1.0/projects/sys-ic/repos/foobar/branches':
            return json.loads('''
{
    "size": 1,
    "limit": 25,
    "isLastPage": true,
    "values": [
        {
            "id": "refs/heads/master",
            "displayId": "master",
            "type": "BRANCH",
            "latestCommit": "8d51122def5632836d1cb1026e879069e10a1e13",
            "latestChangeset": "8d51122def5632836d1cb1026e879069e10a1e13",
            "isDefault": true
        },
        {
            "id": "refs/heads/develop",
            "displayId": "develop",
            "type": "BRANCH",
            "latestCommit": "8d51122def5632836d1cb1026e879069e10a1e13",
            "latestChangeset": "8d51122def5632836d1cb1026e879069e10a1e13",
            "isDefault": false
        },
        {
            "id": "refs/heads/feature/xyz",
            "displayId": "feature/xyz",
            "type": "BRANCH",
            "latestCommit": "8d51122def5632836d1cb1026e879069e10a1e13",
            "latestChangeset": "8d51122def5632836d1cb1026e879069e10a1e13",
            "isDefault": false
        }


    ],
    "start": 0
}''')
        elif path ==\
                '/rest/api/1.0/projects/sys-ic/repos/foobar/pull-requests':
            return json.loads('''
{
    "size": 1,
    "limit": 25,
    "isLastPage": true,
    "values": [
        {
            "id": 101,
            "version": 1,
            "title": "Talking Nerdy",
            "description": "It’s a kludge, but put the tuple from the databas",
            "state": "OPEN",
            "open": true,
            "closed": false,
            "createdDate": 1359075920,
            "updatedDate": 1359085920,
            "fromRef": {
                "id": "refs/heads/feature/xyz",
                "repository": {
                    "slug": "foobar",
                    "name": null,
                    "project": {
                        "key": "sys-ic"
                    }
                }
            },
            "toRef": {
                "id": "refs/heads/master",
                "repository": {
                    "slug": "foobar",
                    "name": null,
                    "project": {
                        "key": "sys-ic"
                    }
                }
            },
            "locked": false,
            "author": {
                "user": {
                    "name": "tom",
                    "emailAddress": "tom@example.tests",
                    "id": 115026,
                    "displayName": "Tom",
                    "active": true,
                    "slug": "tom",
                    "type": "NORMAL"
                },
                "role": "AUTHOR",
                "approved": true,
                "status": "APPROVED"
            },
            "reviewers": [
                {
                    "user": {
                        "name": "jcitizen",
                        "emailAddress": "jane@example.tests",
                        "id": 101,
                        "displayName": "Jane Citizen",
                        "active": true,
                        "slug": "jcitizen",
                        "type": "NORMAL"
                    },
                    "lastReviewedCommit": "7549846524f8aed2bd1c0249993",
                    "role": "REVIEWER",
                    "approved": true,
                    "status": "APPROVED"
                }
            ],
            "participants": [
                {
                    "user": {
                        "name": "dick",
                        "emailAddress": "dick@example.tests",
                        "id": 3083181,
                        "displayName": "Dick",
                        "active": true,
                        "slug": "dick",
                        "type": "NORMAL"
                    },
                    "role": "PARTICIPANT",
                    "approved": false,
                    "status": "UNAPPROVED"
                },
                {
                    "user": {
                        "name": "harry",
                        "emailAddress": "harry@example.tests",
                        "id": 99049120,
                        "displayName": "Harry",
                        "active": true,
                        "slug": "harry",
                        "type": "NORMAL"
                    },
                    "role": "PARTICIPANT",
                    "approved": true,
                    "status": "APPROVED"
                }
            ],
            "links": {
                "self": [
                    {
                        "href": "http://link/to/pullrequest"
                    }
                ]
            }
        }
    ],
    "start": 0
}

                ''')
        elif path ==\
                '/rest/api/1.0/projects/sys-ic/repos/foobar/pull-requests/101':
            return json.loads('''
{
    "id": 101,
    "version": 1,
    "title": "Talking Nerdy",
    "description": "It’s a kludge, but put the tuple from the databas",
    "state": "OPEN",
    "open": true,
    "closed": false,
    "createdDate": 1359075920,
    "updatedDate": 1359085920,
    "fromRef": {
        "id": "refs/heads/feature/xyz",
        "repository": {
            "slug": "foobar",
            "name": null,
            "project": {
                "key": "sys-ic"
            }
        }
    },
    "toRef": {
        "id": "refs/heads/master",
        "repository": {
            "slug": "foobar",
            "name": null,
            "project": {
                "key": "sys-ic"
            }
        }
    },
    "locked": false,
    "author": {
        "user": {
            "name": "tom",
            "emailAddress": "tom@example.tests",
            "id": 115026,
            "displayName": "Tom",
            "active": true,
            "slug": "tom",
            "type": "NORMAL"
        },
        "role": "AUTHOR",
        "approved": true,
        "status": "APPROVED"
    },
    "reviewers": [
        {
            "user": {
                "name": "jcitizen",
                "emailAddress": "jane@example.tests",
                "id": 101,
                "displayName": "Jane Citizen",
                "active": true,
                "slug": "jcitizen",
                "type": "NORMAL"
            },
            "lastReviewedCommit": "7549846524f8aed2bd1c0249993ae1bf9d3c9998",
            "role": "REVIEWER",
            "approved": true,
            "status": "APPROVED"
        }
    ],
    "participants": [
        {
            "user": {
                "name": "dick",
                "emailAddress": "dick@example.tests",
                "id": 3083181,
                "displayName": "Dick",
                "active": true,
                "slug": "dick",
                "type": "NORMAL"
            },
            "role": "PARTICIPANT",
            "approved": false,
            "status": "UNAPPROVED"
        },
        {
            "user": {
                "name": "harry",
                "emailAddress": "harry@example.tests",
                "id": 99049120,
                "displayName": "Harry",
                "active": true,
                "slug": "harry",
                "type": "NORMAL"
            },
            "role": "PARTICIPANT",
            "approved": true,
            "status": "APPROVED"
        }
    ],
    "links": {
        "self": [
            {
                "href": "http://link/to/pullrequest"
            }
        ]
    }
}
                ''')
        elif path ==\
                '/rest/api/1.0/projects/sys-ic/repos/foobar/pull-requests/'\
                '101/merge':
            return json.loads('''
{
    "canMerge": false,
    "conflicted": true,
    "outcome": "CONFLICTED",
    "vetoes": [
        {
            "summaryMessage": "You may not merge after 6pm on a Friday.",
            "detailedMessage": "It is likely that your Blood Alcohol Content"
        }
    ]
}
                ''')
        else:
            return None
