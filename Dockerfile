# Build with 'docker build -t zuuldev .'
# Run tests with 'docker run --interactive -v $PWD:/zuul -u $(id -u) zuuldev tox'
FROM ubuntu
RUN apt-get update
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server zookeeperd python2.7 build-essential wget
RUN wget https://bootstrap.pypa.io/get-pip.py
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y python lsb-release sudo python2.7-dev git python3-dev python
RUN python get-pip.py
RUN pip install bindep
RUN pip install tox
ADD ./bindep.txt /zuul-bindep.txt
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y $(bindep -f /zuul-bindep.txt -b test)
RUN mkdir /var/run/mysqld && chown mysql.mysql /var/run/mysqld
ADD ./tools /tools 
RUN /tools/start-daemons.sh && sleep 1 ; /tools/test-setup.sh
VOLUME /zuul
WORKDIR /zuul
CMD tox
