%cd /content/KPSML-X

fixed_dockerfile = """FROM nanthakps/kpsmlx:heroku_v2

WORKDIR /usr/src/app

RUN chmod 777 /usr/src/app

COPY requirements.txt .

RUN pip3 install --upgrade setuptools pip
RUN pip3 install --use-pep517 pymediainfo pyaes
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "start.sh"]
"""

with open("Dockerfile", "w") as f:
    f.write(fixed_dockerfile)

print("Dockerfile patched successfully!")

!echo "----- Dockerfile -----"
!cat Dockerfile
