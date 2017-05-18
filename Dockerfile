FROM alpine:3.5

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
        py-pip \
        py-virtualenv \
        unzip


### requirements ###

ENV DEV_PACKAGES=" \
                 alpine-sdk \
                 libffi-dev \
                 gcc \
                 gmp-dev \
                 openssl-dev \
                 python-dev \
                 "

# For faster development cycle the dependencies are installed separately from
# zuul itself. This way these layers can be taken from the docker cache if
# there are only changes to the zuul source.
COPY requirements.txt /tmp/

RUN \
    apk add --update --no-cache $DEV_PACKAGES && \
    virtualenv /opt/zuul && \
    /opt/zuul/bin/pip install -U -r /tmp/requirements.txt && \
    /opt/zuul/bin/pip install pytz && \
    # install logstash_formatter to support structured json logging
    /opt/zuul/bin/pip install logstash_formatter && \
    apk del --purge $DEV_PACKAGES

# add tini for zombie reaping as zuul (executor) also launches further processes
# refer to https://blog.phusion.nl/2015/01/20/docker-and-the-pid-1-zombie-reaping-problem/
RUN apk add --update --no-cache tini


### zuul ###

RUN mkdir /opt/zuul-source
COPY . /opt/zuul-source


RUN cd /opt/zuul-source && \
    /opt/zuul/bin/pip install -e .


# install zuul
RUN ln -s /opt/zuul/bin/zuul* /usr/local/bin/ && \
    ln -s /opt/zuul/bin/ansible* /usr/bin/

# create needed directories
RUN mkdir -p /etc/zuul \
             /var/lib/zuul/launcher-git \
             /var/lib/zuul/times \
             /var/log/zuul-executor \
             /var/log/zuul-merger \
             /var/log/zuul-scheduler \
             /mnt/zuul/state


# create zuul user and chown stuff
RUN adduser -S -u 1000 zuul && \
    addgroup zuul && \
    mkdir -p /home/zuul && \
    chown -R zuul:zuul \
                       /home/zuul \
                       /mnt/zuul \
                       /var/lib/zuul \
                       /var/log/zuul-executor \
                       /var/log/zuul-merger \
                       /var/log/zuul-scheduler

ENTRYPOINT ["/sbin/tini", "-g", "--"]

USER zuul
