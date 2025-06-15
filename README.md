# Docker Trim

A Docker container optimization tool that uses dynamic analysis to identify unnecessary files and reduce container size.

## Overview

Docker Trim analyzes running containers using `strace` to track file access patterns during execution. This data can be used to identify which files are actually needed by the application, enabling creation of smaller, more efficient Docker images.

**⚠️ Work in Progress**: Currently only prints file access information to console. Container trimming functionality is under development.

## Features

- **Dynamic Analysis**: Uses `strace` to monitor file system calls during container execution
- **Lambda Support**: Built-in support for testing AWS Lambda functions in containers
- **Memory Monitoring**: Tracks container memory usage during execution
- **File Access Filtering**: Filters out common system directories to focus on application files

## Project Structure

```
.
├── init.py                 # Main DockerTrim class and analysis logic
├── README.md              # This file
└── example/               # Example Lambda function for testing
    ├── lambda_function.py # Sample Python Lambda function using Gemini AI
    ├── Dockerfile         # Container definition with strace
    └── requirements.txt   # Python dependencies
```

## Requirements

- Docker
- Python 3.x
- Python packages:
  - `docker` - Docker Python SDK
  - `requests` - HTTP client for Lambda invocation

## Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd docker-trim
   ```

2. Install Python dependencies:

   ```bash
   pip install docker requests
   ```

3. Ensure Docker is running on your system

## Usage

1. **Build your Docker image** (hardcoded example provided uses a Lambda function):

   ```bash
   cd example
   docker build -t docker-image:test .
   ```

2. **Update the image name** in `init.py` (line 299):

   ```python
   trimmer = DockerTrim("docker-image:test")
   ```

3. **Run the analysis**:
   ```bash
   python init.py
   ```

## Current Output

The tool currently provides:

- **Container Information**: Original entrypoint and command
- **Lambda Invocation Results**: Status and response from Lambda function
- **File Access Analysis**: List of files accessed during container execution (filtered)
- **Memory Usage Statistics**: Container memory consumption
- **Cleanup**: Automatic container and temporary file cleanup

## Example Output

```
Image Original Entrypoint: ['/lambda-entrypoint.sh']
Image Original Cmd: ['app.lambda_handler']
Container started: abc123...

--- Triggering Lambda ---
Lambda invocation status: 200
Lambda output snippet: {"response": "Hello! I'm Gemini, an AI assistant..."}

--- Retrieving strace log ---
Retrieved strace log (15432 bytes). Parsing...
Found 247 raw file access paths.

--- Files Accessed by Lambda (Filtered) ---
/opt/python/lib/python3.11/site-packages/google/...
/var/runtime/lambda_function.py
/var/task/app.py
...
Total filtered unique file accesses: 3192

--- Memory Usage ---
Memory Stats: {'memory_usage_bytes': 52428800, 'memory_limit_bytes': None, 'usage_pct': None}
```

## How It Works

1. **Container Wrapping**: Creates a wrapper script that runs `strace` around the original container command
2. **Dynamic Execution**: Starts the container and triggers the application (Lambda function)
3. **File Monitoring**: Captures all file system calls using `strace`
4. **Analysis**: Parses the strace output to identify accessed files
5. **Filtering**: Removes common system directories to focus on application-specific files

## System Directories Filtered

The tool automatically filters out accesses to common system directories:

- `/dev`, `/proc`, `/sys`
- `/tmp`, `/var/log`, `/run`
- `/var/tmp`, `/var/lib`
- `/etc/ssl`, `/usr/share/ca-certificates`

## Roadmap

- [ ] Generate optimised Dockerfiles based on analysis
- [ ] Support for different application types beyond Lambda
- [ ] Automated image building and comparison
- [ ] Package dependency analysis

## Contributing

This project is currently in early development. Contributions and feedback are welcome!

## Troubleshooting

**Container fails to start**: Ensure your Docker image has `strace` installed and the correct entrypoint/cmd configuration.

**Empty strace log**: Check that the container is actually executing and the strace wrapper script has proper permissions.

**Lambda invocation fails**: Verify the container is exposing the correct port (9000) and the Lambda runtime is properly configured.
