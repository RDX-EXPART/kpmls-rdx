FROM nanthakps/kpsmlx:heroku_v2

WORKDIR /usr/src/app
RUN chmod 777 /usr/src/app

COPY . .

RUN pip3 install --upgrade setuptools pip
RUN pip3 install --use-pep517 pymediainfo pyaes
RUN pip3 install --no-cache-dir -r requirements.txt


CMD ["bash", "start.sh"]
