# Use an official Python runtime as a parent image
FROM ubuntu:jammy

# Set environment variables
ENV MYSQL_ROOT_PASSWORD=rootpassword

# Install MySQL, Python, and pip
RUN apt-get update && \
    apt-get install -y mysql-server python3 python3-pip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install any Python packages as needed
RUN pip3 install mysql-connector-python

# Install Python dependencies
COPY requirements.txt .
WORKDIR /
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container
COPY . .

# Command to run when the container starts
CMD ["mysqld", "--default-authentication-plugin=mysql_native_password"]
