FROM python:3.6
ENV PYTHONUNBUFFERED 1
RUN apt-get update && \
    apt-get install nodejs npm -y && \
    apt-get clean
RUN npm install -g pm2
RUN mkdir /elastic_apis
WORKDIR /elastic_apis
ADD . /elastic_apis/
RUN pip3.6 install --upgrade virtualenv
RUN virtualenv -p python3.6 fenve
RUN . /elastic_apis/fenve/bin/activate
RUN pip3.6 install -r requirements.txt
RUN pm2 start echo --interpreter=python
EXPOSE 8000
ENTRYPOINT ["pm2-runtime", "start", "ecosystem.config.js"]