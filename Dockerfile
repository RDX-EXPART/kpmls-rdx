FROM nanthakps/kpsmlx:heroku_v2

WORKDIR /usr/src/app

# Permission
RUN chmod 777 /usr/src/app

# System packages (VERY IMPORTANT)
RUN apt-get update && apt-get install -y mediainfo

# Copy requirements first (cache optimization)
COPY requirements.txt .

# Upgrade pip tools (safe)
RUN pip3 install --upgrade pip wheel

# Install dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Start bot
CMD ["bash", "start.sh"]
