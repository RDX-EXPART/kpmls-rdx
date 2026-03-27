FROM nanthakps/kpsmlx:heroku_v2

WORKDIR /usr/src/app

# Permission
RUN chmod 777 /usr/src/app

# System packages
RUN apt-get update && apt-get install -y mediainfo

# Copy requirements
COPY requirements.txt .

# Install critical build deps FIRST
RUN pip3 install --upgrade pip wheel setuptools_scm vcs_versioning

# Install باقي packages
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

CMD ["bash", "start.sh"]
