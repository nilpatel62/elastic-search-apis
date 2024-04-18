#!/bin/bash

# Update the package list
sudo apt-get update

# Install necessary prerequisites for Docker
sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common

# Check if Docker is already installed
if ! [ -x "$(command -v docker)" ]; then
  # Add Docker’s official GPG key
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -

  # Add Docker repository
  sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"

  # Update the package database with Docker packages from the newly added repo
  sudo apt-get update

  # Install Docker
  sudo apt-get install -y docker-ce
fi

# Start Docker if it's not running
sudo systemctl start docker

# Enable Docker service to start on boot
sudo systemctl enable docker


# Pull and run Elasticsearch container, binding to all network interfaces
sudo docker run -d --name elasticsearch --net elastic \
    -p 0.0.0.0:9200:9200 \
    -p 0.0.0.0:9300:9300 \
    -e "discovery.type=single-node" \
    -e "network.host=0.0.0.0" \
    -it docker.elastic.co/elasticsearch/elasticsearch:8.13.2


# Wait for Elasticsearch to start
echo "Waiting for Elasticsearch to start..."
sleep 120  # Wait 30 seconds. Adjust this timing as necessary.

# Generate passwords for Elasticsearch
echo "Generating passwords for Elasticsearch..."
PASSWORD=$(sudo docker exec elasticsearch bin/elasticsearch-setup-passwords auto --batch | grep "PASSWORD elastic =" | awk '{print $4}')

# Check if the password was retrieved
if [ -z "$PASSWORD" ]; then
  echo "Failed to retrieve the Elasticsearch password."
  exit 1
else
  echo "Elasticsearch password retrieved successfully."
fi

# Function to pull and run Docker images as containers
pull_and_run_container() {
  IMAGE_NAME=$1
  CONTAINER_NAME=$2

  # Pull the Docker image
  echo "Pulling image ${IMAGE_NAME}..."
  sudo docker pull ${IMAGE_NAME}

  # Run the Docker container
  echo "Running container ${CONTAINER_NAME}..."
  sudo docker run -d --name ${CONTAINER_NAME} ${IMAGE_NAME}
}

# Define the path for the Zeek logs directory on the host
ZEEK_LOGS_DIR="$(pwd)/zeek-logs"

# Create the Zeek logs directory if it does not exist
mkdir -p "$ZEEK_LOGS_DIR"


# Set the names of the images
ZEEK_IMAGE="blacktop/zeek"  # replace with the specific version you need
SURICATA_IMAGE="jasonish/suricata"  # replace with the specific version you need
TSHARK_IMAGE="wireshark/tshark"  # replace with the specific version you need
FILEBEAT_IMAGE="elastic/filebeat"  # replace with the specific version you need

# Pull and run the Zeek container
echo "Starting zeek container..."
# Run Zeek in a Docker container with specified configurations
sudo docker run -d --name zeek \
    -v "${ZEEK_LOGS_DIR}:/var/log/zeek" \
    ${IMAGE_NAME}

# Pull and run the Suricata container
SURICATA_LOG_DIR="$(pwd)/logs"
mkdir -p "$SURICATA_LOG_DIR"

# Run Suricata container with specified options
echo "Starting Suricata container..."
docker run -d --rm -it --net=host --cap-add=net_admin --cap-add=net_raw --cap-add=sys_nice \
    -v "${LOG_DIR}:/var/log/suricata" \
    $SURICATA_IMAGE -i docker0

# Pull and run the Tshark container
pull_and_run_container ${TSHARK_IMAGE} tshark

# Install Filebeat
echo "Installing Filebeat..."
curl -L -O https://artifacts.elastic.co/downloads/beats/filebeat/filebeat-7.9.3-amd64.deb
sudo dpkg -i filebeat-7.9.3-amd64.deb

# Create a Filebeat configuration file
FILEBEAT_CONFIG="/etc/filebeat/filebeat.yml"


# Check if filebeat.yml already exists
if [ -f "$FILEBEAT_CONFIG" ]; then
  echo "Updating Filebeat config file at ${FILEBEAT_CONFIG}..."
  # Append Elasticsearch output settings
  sudo bash -c "cat >> ${FILEBEAT_CONFIG}" << EOF
output.elasticsearch:
  hosts: ["https://0.0.0.0:9200"]
  username: "elastic"
  password: "$PASSWORD"
  ssl.verification_mode: "none"
EOF
  fi
else
  echo "Creating Filebeat config file at ${FILEBEAT_CONFIG}..."
  sudo bash -c "cat > ${FILEBEAT_CONFIG}" << EOF
filebeat.inputs:
- type: filestream
  id: my-filestream-id
  enabled: true
  paths:
    - /var/log/*.log

filebeat.config.modules:
  path: ${path.config}/modules.d/*.yml
  reload.enabled: false

output.elasticsearch:
  hosts: ["https://0.0.0.0:9200"]
  username: "elastic"
  password: "$PASSWORD"
  ssl.verification_mode: "none"
EOF
fi


# Enable and start Filebeat service
sudo systemctl enable filebeat
sudo systemctl start filebeat

# Confirm the Filebeat service is running
if systemctl status filebeat &> /dev/null; then
    echo "Filebeat service is running."
else
    echo "Failed to start Filebeat service. Please check the status manually."
fi

echo "All containers are up and running."
