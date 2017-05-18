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
    python3 -m venv /opt/zuul && \
    /opt/zuul/bin/pip install --upgrade pip && \
    /opt/zuul/bin/pip install -r /tmp/requirements.txt --install-option="--install-scripts=/usr/bin" && \
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


#RUN /opt/zuul/bin/pip install /opt/zuul-source
RUN cd /opt/zuul-source && . /opt/zuul/bin/activate && python3 setup.py install --install-scripts /usr/bin


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

ENTRYPOINT ["/sbin/tini", "-g", "--"]

USER zuul
