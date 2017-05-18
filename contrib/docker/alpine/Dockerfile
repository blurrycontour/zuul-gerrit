FROM alpine:3.6

# install required software packages
RUN apk add --update --no-cache \
        curl \
        gettext \
        git \
        libffi \
        gmp \
        openssh \
        openssl \
        procps \
        python \
        python3 \
        rsync \
        unzip


### requirements ###

ENV DEV_PACKAGES=" \
                 alpine-sdk \
                 libffi-dev \
                 gcc \
                 gmp-dev \
                 openssl-dev \
                 python3-dev \
                 "

# For faster development cycle the dependencies are installed separately from
# zuul itself. This way these layers can be taken from the docker cache if
# there are only changes to the zuul source.
COPY requirements.txt /tmp/

RUN \
    apk add --update --no-cache $DEV_PACKAGES && \
    pip3 install --upgrade pip setuptools && \
    pip3 install -r /tmp/requirements.txt && \
    # install logstash_formatter to support structured json logging
    pip3 install logstash_formatter pywinrm && \
    apk del --purge $DEV_PACKAGES

# TODO(tobiash): The Github3.py dependency is currently incompatible with the
#                install-scripts option. So we must create the important
#                symlinks ourself. This should be switched to use the
#                install-scripts option when it is compatible.
#RUN ln -s /opt/zuul/bin/ansible* /usr/bin/

# add tini for zombie reaping as zuul (executor) also launches further processes
# refer to https://blog.phusion.nl/2015/01/20/docker-and-the-pid-1-zombie-reaping-problem/
RUN apk add --update --no-cache tini


### zuul ###

RUN mkdir -p /opt/zuul-source
COPY . /opt/zuul-source


#RUN cd /opt/zuul-source && /opt/zuul/bin/python3 setup.py install --install-scripts /usr/bin
RUN cd /opt/zuul-source && python3 setup.py install

# HACK(tobiash): in openshift somehow the static part is omitted
RUN cp -r /opt/zuul-source/zuul/web/static /usr/lib/python3.6/site-packages/zuul/web/static

# create needed directories
RUN mkdir -p /etc/zuul \
             /var/lib/zuul/launcher-git \
             /var/lib/zuul/times \
             /var/log/zuul-executor \
             /var/log/zuul-merger \
             /var/log/zuul-scheduler \
             /mnt/zuul/state


# create zuul user and chown stuff
RUN adduser -D -u 1000 zuul && \
    chown -R zuul:zuul \
                       /home/zuul \
                       /mnt/zuul \
                       /var/lib/zuul \
                       /var/log/zuul-executor \
                       /var/log/zuul-merger \
                       /var/log/zuul-scheduler

