# PowerShell script to download Delta jar files

# Create directory if it doesn't exist
if (-not (Test-Path -Path "delta_jar")) {
    New-Item -Path "delta_jar" -ItemType Directory
    Write-Output "Created directory: delta_jar"
}

# Download delta-core jar
$deltaCorePath = "delta_jar/delta-core_2.12-2.1.0.jar"
$deltaCoreUrl = "https://repo1.maven.org/maven2/io/delta/delta-core_2.12/2.1.0/delta-core_2.12-2.1.0.jar"

Write-Output "Downloading Delta Core jar..."
Invoke-WebRequest -Uri $deltaCoreUrl -OutFile $deltaCorePath
Write-Output "Downloaded: $deltaCorePath"

# Download delta-storage jar
$deltaStoragePath = "delta_jar/delta-storage-2.1.0.jar"
$deltaStorageUrl = "https://repo1.maven.org/maven2/io/delta/delta-storage/2.1.0/delta-storage-2.1.0.jar"

Write-Output "Downloading Delta Storage jar..."
Invoke-WebRequest -Uri $deltaStorageUrl -OutFile $deltaStoragePath
Write-Output "Downloaded: $deltaStoragePath"

Write-Output "Download complete!" 