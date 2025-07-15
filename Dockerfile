# Use a newer Debian base image for Python 3.10
# 'bullseye' (Debian 11) is a good stable choice.
# 'bookworm' (Debian 12) is even newer if you prefer.
FROM python:3.10-slim-bullseye

# Update package lists and install git
# No need for apt upgrade -y right after update in a fresh image, update is usually enough
RUN apt update && apt install -y git

# Copy requirements.txt first to leverage Docker caching
COPY requirements.txt /requirements.txt

# Upgrade pip and install Python dependencies
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir -U -r /requirements.txt

# Create and set working directory
# No need for 'RUN cd /' before mkdir /FileToLink
RUN mkdir /FileToLink
WORKDIR /FileToLink

# Copy the rest of your application code into the working directory
COPY . /FileToLink

# Command to run your bot
CMD ["python3", "bot.py"]
