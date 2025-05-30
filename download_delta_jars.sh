#!/bin/bash

# Create directory if it doesn't exist
mkdir -p delta_jar
echo "Created directory: delta_jar"

# Download delta-core jar
DELTA_CORE_PATH="delta_jar/delta-core_2.12-2.1.0.jar"
DELTA_CORE_URL="https://repo1.maven.org/maven2/io/delta/delta-core_2.12/2.1.0/delta-core_2.12-2.1.0.jar"

echo "Downloading Delta Core jar..."
curl -L -o $DELTA_CORE_PATH $DELTA_CORE_URL
echo "Downloaded: $DELTA_CORE_PATH"

# Download delta-storage jar
DELTA_STORAGE_PATH="delta_jar/delta-storage-2.1.0.jar"
DELTA_STORAGE_URL="https://repo1.maven.org/maven2/io/delta/delta-storage/2.1.0/delta-storage-2.1.0.jar"

echo "Downloading Delta Storage jar..."
curl -L -o $DELTA_STORAGE_PATH $DELTA_STORAGE_URL
echo "Downloaded: $DELTA_STORAGE_PATH"

echo "Download complete!" 