# Set the base image to use to Ubuntu
FROM ubuntu:12.04

RUN apt-get update -y
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y wget supervisor unzip ca-certificates

RUN echo 'deb http://repo.acestream.org/ubuntu/ precise main' > /etc/apt/sources.list.d/acestream.list
RUN wget -q -O - http://repo.acestream.org/keys/acestream.public.key | apt-key add -
RUN DEBIAN_FRONTEND=noninteractive apt-get update -y

RUN DEBIAN_FRONTEND=noninteractive apt-get install -y acestream-engine vlc-nox python-gevent
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y python-pip python-dev
#RUN pip install --index-url="https://pypi.python.org/simple/" beautifulsoup4
RUN pip install --index-url="https://pypi.python.org/simple/" --upgrade pip
#RUN pip install scrapy
RUN pip install beautifulsoup4
RUN pip install lxml

RUN mkdir -p /var/run/sshd
RUN mkdir -p /var/log/supervisor

RUN adduser --disabled-password --gecos "" tv

RUN cd /tmp/ && wget https://github.com/ValdikSS/aceproxy/archive/6dff4771c3.zip -O master.zip
RUN cd /tmp/ && unzip master.zip -d /home/tv/
RUN mv /home/tv/aceproxy-* /home/tv/aceproxy-master

RUN echo 'root:password' |chpasswd

ADD acehttp.py /home/tv/aceproxy-master/acehttp.py
ADD supervisord.conf /etc/supervisor/conf.d/supervisord.conf
ADD start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 22 8000 62062

ENTRYPOINT ["/start.sh"]
