import docker
import json
import time
import requests
import re
import os
import tempfile
from docker.errors import APIError, ImageNotFound, NotFound

client = docker.from_env()
COMMON_SYSTEM_DIRS = [
    "/dev", "/proc", "/sys", "/tmp", "/var/log", "/run", "/var/run",
    "/var/tmp", "/var/lib", "/etc/ssl", "/usr/share/ca-certificates"
]
log_path_in_container = "/tmp/strace.log"  # Path inside the container
STRACE_WRAPPER_SCRIPT_CONTENT = f"""#!/bin/bash
set -euo pipefail
# mkdir -p $(dirname {log_path_in_container})
exec /usr/bin/strace -f -e trace=file -o {log_path_in_container} "$@"
"""


class DockerTrim:
    def __init__(self, image: str):
        self.image = image
        self.wrapper_script_path_host = None

    def _get_image_config(self):
        """Inspects the image to get its default ENTRYPOINT and CMD."""
        try:
            image_obj = client.images.get(self.image)
            config = image_obj.attrs.get('Config', {})
            entrypoint = config.get('Entrypoint')
            cmd = config.get('Cmd')
            return entrypoint, cmd
        except ImageNotFound:
            raise RuntimeError(
                f"Image '{self.image}' not found during inspection.")
        except APIError as e:
            raise RuntimeError(
                f"Error inspecting image '{self.image}': {str(e)}")

    def init_container(self):
        container = None
        wrapper_container_path = "/wrapper.sh"

        try:
            original_entrypoint, original_cmd = self._get_image_config()
            print(f"Image Original Entrypoint: {original_entrypoint}")
            print(f"Image Original Cmd: {original_cmd}")
            command_to_wrap = []
            if original_entrypoint:
                if isinstance(original_entrypoint, str):
                    command_to_wrap.append(original_entrypoint)
                else:
                    command_to_wrap.extend(original_entrypoint)

            if original_cmd:
                if isinstance(original_cmd, str):
                    command_to_wrap.append(original_cmd)
                else:
                    command_to_wrap.extend(original_cmd)

            if not command_to_wrap:
                raise RuntimeError(
                    f"Could not determine the command to wrap from image '{self.image}'. Does it have an ENTRYPOINT or CMD?")

            print(f"Command sequence being wrapped: {command_to_wrap}")

            with tempfile.NamedTemporaryFile(mode='w', delete=False, prefix='strace_wrapper_', suffix='.sh') as tmp_file:
                self.wrapper_script_path_host = tmp_file.name
                tmp_file.write(STRACE_WRAPPER_SCRIPT_CONTENT)
            os.chmod(self.wrapper_script_path_host, 0o755)
            print(
                f"Created temporary wrapper script: {self.wrapper_script_path_host}")

            container = client.containers.run(
                image=self.image,
                entrypoint=wrapper_container_path,
                command=command_to_wrap,
                detach=True,
                ports={'8080/tcp': 9000},
                tty=True,
                volumes={
                    self.wrapper_script_path_host: {
                        'bind': wrapper_container_path,
                        'mode': 'ro'  # Read-only mount
                    }
                },

            )
            print(f"Container started: {container.id}")
            time.sleep(5)

            container.reload()
            if container.status != 'running':
                logs = container.logs().decode()
                print("Container logs on startup failure:")
                print(logs)
                raise RuntimeError(
                    f"Container failed to start. Status: {container.status}")

            return container

        except ImageNotFound:
            raise RuntimeError(f"Image '{self.image}' not found.")
        except APIError as e:
            if container:
                try:
                    logs = container.logs().decode()
                    print("Container logs on API error during run:")
                    print(logs)
                except:
                    print("Could not retrieve container logs.")
            raise RuntimeError(f"Error starting container: {str(e)}")
        except Exception as e:
            raise RuntimeError(
                f"An unexpected error occurred during container initialization: {str(e)}")

    def stop_container(self, container):
        try:
            print(f"Stopping container {container.id}...")
            container.stop()
            print(f"Container {container.id} stopped.")
        except NotFound:
            print(f"Error: Container {container.id} not found during stop.")
        except APIError as e:
            print(f"Error stopping container {container.id}: {str(e)}")
        except Exception as e:
            print(
                f"An unexpected error occurred while stopping container {container.id}: {str(e)}")

    def remove_container(self, container):
        try:
            print(f"Removing container {container.id}...")
            container.remove(force=True)
            print(f"Container {container.id} removed.")
        except NotFound:
            print(f"Error: Container {container.id} not found during remove.")
        except APIError as e:
            print(f"Error removing container {container.id}: {str(e)}")
        except Exception as e:
            print(
                f"An unexpected error occurred while removing container {container.id}: {str(e)}")

    def cleanup(self, container=None):
        """Stops and removes the container and cleans up temporary files."""
        if container:
            self.stop_container(container)
            self.remove_container(container)

        if self.wrapper_script_path_host and os.path.exists(self.wrapper_script_path_host):
            try:
                os.unlink(self.wrapper_script_path_host)
                print(
                    f"Cleaned up temporary wrapper script: {self.wrapper_script_path_host}")
            except OSError as e:
                print(
                    f"Error cleaning up temporary wrapper script {self.wrapper_script_path_host}: {e}")
            self.wrapper_script_path_host = None

    def get_memory_usage(self, container_id: str):
        try:
            container = client.containers.get(container_id)
            stats = container.stats(stream=False)
            mem_usage = stats['memory_stats']['usage']

            mem_limit = stats['memory_stats'].get(
                'limit', None)  # limit might not be set

            if mem_limit is None or mem_limit == 0:
                usage_pct = None
                print("Warning: Container memory limit not found or is 0.")
            else:
                usage_pct = round((mem_usage / mem_limit) * 100, 2)

            return {
                "memory_usage_bytes": mem_usage,
                "memory_limit_bytes": mem_limit,
                "usage_pct": usage_pct
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def parse_strace_file_accesses(log: str):
        accessed_files = set()
        file_access_syscalls = r'(openat|open|access|stat|faccessat|lstat|newfstatat|fstat|readlinkat|readlink|statx)'
        regex = re.compile(rf'{file_access_syscalls}.*?"(.*?)"')

        for line in log.splitlines():
            match = regex.search(line)
            if match:
                filepath = match.group(2)
                if filepath:
                    accessed_files.add(filepath)
        return accessed_files

    def trigger_lambda_in_container(self):
        try:
            response = requests.post(
                "http://localhost:9000/2015-03-31/functions/function/invocations",
                json={"input_text": "Introduce yourself in 2 sentences."},
            )
            if response.status_code >= 300:
                return response.status_code, f"Error response from Lambda: {response.text}"

            return response.status_code, response.text
        except requests.exceptions.Timeout:
            return 504, "Timeout connecting to or receiving response from Lambda."
        except requests.RequestException as e:
            return 500, f"Error calling Lambda endpoint: {str(e)}"

    def list_container_files(self, container, path="/"):
        try:
            exit_code, output = container.exec_run(f"find \"{path}\" -type f")
            if exit_code == 0:
                files = output.decode().splitlines()
                return set(f for f in files if f)
            else:
                print(
                    f"Error listing files in container at {path}. Exit code: {exit_code}")
                print(f"Output: {output.decode()}")
                return set()
        except Exception as e:
            print(f"Exception listing files in container: {str(e)}")
            return set()

    def retrieve_strace_log(self, container, log_path=log_path_in_container):
        try:
            exit_code, output = container.exec_run(f"cat {log_path}")
            if exit_code == 0:
                return output.decode()
            else:
                print(
                    f"Error retrieving strace log from {log_path}. Exit code: {exit_code}")
                print(f"Output: {output.decode()}")
                return ""
        except Exception as e:
            print(f"Exception retrieving strace log: {str(e)}")
            return ""

    def compare_file_sets(self, before: set, after: set):
        deleted = before - after
        added = after - before
        return {"added_files": list(added), "deleted_files": list(deleted)}

    @staticmethod
    def is_ignorable(filepath):
        if not filepath.startswith('/'):
            return False  # Don't ignore relative paths unless they map to system dirs

        return any(filepath.startswith(prefix) for prefix in COMMON_SYSTEM_DIRS)

    @staticmethod
    def filter_accessed_files(accessed_files):
        return {f for f in accessed_files if not DockerTrim.is_ignorable(f)}


container = None
trimmer = None

try:
    trimmer = DockerTrim("docker-image:test")
    container = trimmer.init_container()

    if container:
        print("\n--- Triggering Lambda ---")
        status, output = trimmer.trigger_lambda_in_container()
        print(f"Lambda invocation status: {status}")
        print(f"Lambda output snippet: {output[:500]}...")

        if status != 200:
            print("Lambda invocation failed. Cannot proceed with log analysis.")
            try:
                full_logs = container.logs().decode()
                print("\n--- Full container logs ---")
                print(full_logs)
                print("---------------------------")
            except Exception as log_e:
                print(f"Could not retrieve full container logs: {log_e}")

        else:
            print("\n--- Retrieving strace log ---")
            log = trimmer.retrieve_strace_log(container)
            if not log:
                print("Strace log is empty or could not be retrieved.")
            else:
                print(f"Retrieved strace log ({len(log)} bytes). Parsing...")
                raw_accesses = DockerTrim.parse_strace_file_accesses(
                    log)  # Call static method via class
                print(f"Found {len(raw_accesses)} raw file access paths.")
                filtered_accesses = DockerTrim.filter_accessed_files(
                    raw_accesses)  # Call static method via class
                print("\n--- Files Accessed by Lambda (Filtered) ---")
                for f in sorted(list(filtered_accesses)):
                    print(f)
                print(
                    f"Total filtered unique file accesses: {len(filtered_accesses)}")

        print("\n--- Memory Usage ---")
        mem_stats = trimmer.get_memory_usage(container.id)
        print(f"Memory Stats: {mem_stats}")

except RuntimeError as e:
    print(f"Script error: {e}")
except Exception as e:
    print(f"An unexpected script error occurred: {e}")
finally:
    if trimmer:
        trimmer.cleanup(container)
