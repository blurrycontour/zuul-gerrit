import github3
import cachecontrol
from cachecontrol.cache import DictCache
import logging
import time

url = 'https://example.com'
api_token = 'xxxx'


# Send the logs to stderr as well
stream_handler = logging.StreamHandler()


logger_urllib3 = logging.getLogger('requests.packages.logger_urllib3')
# logger_urllib3.addHandler(stream_handler)
logger_urllib3.setLevel(logging.DEBUG)

logger = logging.getLogger('github3')
# logger.addHandler(stream_handler)
logger.setLevel(logging.DEBUG)


github = github3.GitHubEnterprise(url)


cache_adapter = cachecontrol.CacheControlAdapter(
            DictCache(),
            cache_etags=True)

github.session.mount('http://', cache_adapter)
github.session.mount('https://', cache_adapter)


github.login(token=api_token)

i = 0
while True:
    pr = github.pull_request('ORG', 'PROJECT', 3)
    prdict = pr.as_dict()
    issue = pr.issue()
    labels = list(issue.labels())
    print(labels)
    i+=1
    print(i)
    time.sleep(1)
