FROM nanthakps/kpsmlx:heroku_v2

WORKDIR /usr/src/app

RUN chmod 777 /usr/src/app

# mediainfo fix
RUN apt-get update && apt-get install -y mediainfo

COPY requirements.txt .

# install build deps আগে
RUN pip3 install --upgrade pip wheel setuptools_scm vcs_versioning

# 🔥 MAIN FIX HERE
RUN pip3 install --no-cache-dir --no-build-isolation -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]
