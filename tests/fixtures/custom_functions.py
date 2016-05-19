def select_debian_node(item, params):
    params['ZUUL_NODE'] = 'debian'


def alter_job_names(item, job, params):
    prefix = 'should-be-'
    if job.name.startswith(prefix):
        new_name = job.name[len(prefix):]
        params['ZUUL_REMOTEJOB'] = new_name
        params['ZUUL_DISPLAYNAME'] = 'display-' + new_name
