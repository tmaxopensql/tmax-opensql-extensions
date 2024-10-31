from datetime import datetime
from os import path, makedirs, getenv
from _pyio import BufferedWriter

import yaml, docker, docker.errors
import docker.models
import docker.models.containers
from docker.models.containers import Container, ExecResult

import logging, traceback
import requests
import json

# label variables for convenience and readability
os = 'os'
database = 'database'
extensions = 'extensions'
repository = 'repository'

name = 'name'
value = 'value'
group = 'group'
build = 'build'
source = 'source'
version = 'version'
major_version = 'major_version'
minor_version = 'minor_version'

common = 'common'

# input & metadata
input_file_name = 'input.yaml'
metadata_name = 'builder.yaml'
metadata = {}
spec = {}

# token
upload_access_token = None

# log directory
log_directory_name = 'logs'

def main():

    if not path.isfile(input_file_name):
        print(f'[ERROR] please set an input file (file name must be "{input_file_name}")')
        return

    if not path.isfile(metadata_name):
        print(f'[ERROR] please set an metadata (file name must be "{metadata_name}")')
        return

    global metadata, spec, upload_access_token
    metadata = read_yaml(metadata_name)
    spec = read_yaml(input_file_name)

    if len(spec) == 0 or len(metadata) == 0:
        print(f'[ERROR] loading {input_file_name} or {metadata_name} is failed.')
        return

    if os not in spec or spec[os][name] not in metadata[os]:
        print(f'[ERROR] valid OS must be set. Please input an OS argument. (available os: {metadata[os].keys()})')
        return

    if database not in spec or spec[database][name] not in metadata[database]:
        print(f'[ERROR] valid Database must be set. Please input Database argument. (available database: {metadata[database].keys()})')
        return

    upload_access_token = getenv(metadata['upload_token_env_key'])

    if upload_access_token is None:
        print(f'[ERROR] Please check an environment variable of access token value for upload. (env name: {metadata['upload_token_env_key']})')
        return

    if spec[database][name] == 'postgresql':
        pg_extension_build_main()

    return

def pg_extension_build_main():

    format_arguments = {
        'os_name': spec[os][name],
        'os_version': spec[os][version],
        'os_major_version': spec[os][version].split('.')[0],
        'db_version': spec[database][version],
        'db_major_version': spec[database][version].split('.')[0]
    }

    build_target_extensions = []
    for extension in spec[extensions]:

        format_arguments[name] = extension[name]
        format_arguments[version] = extension[version]
        format_arguments[major_version],\
        format_arguments[minor_version], *_ = extension[version].split('.')

        prebuilt_extension_url = metadata['prebuilt_extension_download_url'].format(**format_arguments)

        already_prebuilt_available = is_file_downloadable(prebuilt_extension_url)

        if already_prebuilt_available:
            print(f'[INFO] {extension[name]}:{extension[version]} for {spec[os][name]}{spec[os][version]}, pg{spec[database][version]} is already available. skip this extension build step.')
            continue

        build_source_url = extension[source].format(**format_arguments)
        build_source_available = is_file_downloadable(build_source_url)

        if not build_source_available:
            print(f'[WARN] {extension[name]}:{extension[version]} build source url({build_source_url}) is not available. skip this extension build step.')
            continue

        build_target_extensions.append(extension)

    if len(build_target_extensions) == 0:
        print('[INFO] there is no extension need to be built. program exit.')
        return

    docker_client = docker.from_env()
    docker_image = get_os_docker_image(spec[os][name], spec[os][version], docker_client)

    if docker_image is None: return

    container = None
    container_log = None

    try:
        print(f'[INFO] make a docker container...')
        container = docker_client.containers.run(docker_image, '/bin/bash', detach=True, tty=True)

        # save the logs of the docker container
        if not path.isdir(log_directory_name):
            makedirs(log_directory_name)

        container_log = open(f'{log_directory_name}/{datetime.now()}.log', 'ab')

        # 0. epel settings if needed
        success = set_epel_repository(spec[os][name], spec[os][version].split('.')[0], container, container_log)

        if not success: return

        # 1. pg install
        success = install_postgresql(format_arguments, container, container_log)

        if not success: return

        # 2. pg extension build and upload
        build_and_upload_pg_extensions(build_target_extensions, format_arguments, container, container_log)

    except Exception as e:
        logging.error(traceback.format_exc())

    finally:

        if container_log is not None:
            container_log.close()

        if container is not None:

            container.kill()
            container.remove()

def read_yaml(file_path: str) -> dict:

    if file_path is None: return None

    file = open(file_path, 'r')

    data = yaml.load(file, Loader=yaml.BaseLoader)

    return data

def is_file_downloadable(url: str) -> bool:
    try:
        response = requests.head(url, allow_redirects=True)

        if response.status_code == 200:

            content_type = response.headers.get('Content-Type', '').lower()

            if 'text' not in content_type and 'html' not in content_type:
                return True

    except requests.RequestException as e:

        print(f"[ERROR] check file is failed.\n{e}")

    return False

def get_os_docker_image(os_name, os_version, docker_client):

    docker_image = None
    try:

        os_repository = metadata[os][os_name][repository][value]

        docker_image = docker_client.images.get(os_repository+':'+os_version)

    except docker.errors.ImageNotFound:

        print(f'[WARN] docker image ({os_repository}:{os_version}) does not exist in this machine. docker pull will be started.')

    if docker_image is None:
        try:

            docker_image = docker_client.images.pull(os_repository, os_version)

            print(f'[INFO] docker image ({os_repository}:{os_version}) pull is completed.')

        except docker.errors.NotFound:

            print(f'[ERROR] docker image ({os_repository}:{os_version}) pull is failed. please check the os name and version.')
            return None

    return docker_image

def execute_and_log_container(command: str, container: Container, log: BufferedWriter, workdir: str=None) -> ExecResult:

    log.write(f'\n[{datetime.now()}] {command}\n'.encode())

    result = container.exec_run(command, workdir=workdir)

    log.write(result.output)

    return result

def set_epel_repository(os_name, os_major_version, container, container_log):

    if 'epel_settings' not in metadata[os][os_name]:
        return True

    print(f'[INFO] redhat os epel(CRB) setting...')

    epel_setting = metadata[os][os_name]['epel_settings']

    if common in epel_setting:
        commands = epel_setting[common]
    else:
        commands = epel_setting[os_major_version]

    for command in commands:
        result = execute_and_log_container(command.format(os_major_version=os_major_version), container, container_log)

        if result.exit_code != 0:
            print(f'[ERROR] os epel setting is failed.\n{result.output.decode()}')
            return False

    return True

def install_postgresql(format_arguments: dict, container, container_log):

    print(f'[INFO] install postgresql...')

    install_commands = metadata[database]['postgresql']['install_commands'].get(spec[os][name])

    if install_commands is None:
        os_group = metadata[os][spec[os][name]].get('group')

        if os_group is not None:
            install_commands = metadata[database]['postgresql']['install_commands'].get(os_group)

    if install_commands is None:
        print(f'[ERROR] There is not available install commands for {spec[os][name]}:{spec[os][version]}')
        return False

    for command in install_commands:

        command = command.format(**format_arguments)

        result = execute_and_log_container(command, container, container_log)

        if result.exit_code != 0:
            print(f'[ERROR] command({command}) execution failed.\n{result.output.decode()}')
            return False

    return True

def build_and_upload_pg_extensions(build_target_extensions: list, format_arguments: dict, container: Container, container_log):

    for extension in build_target_extensions:

        print(f'[INFO] {extension[name]} {extension[version]} build and upload start...')

        # argument settings for string format parsing
        format_arguments[name] = extension[name]
        format_arguments[version] = extension[version]
        format_arguments[major_version],\
        format_arguments[minor_version], *_ = extension[version].split('.')

        build_source_url = extension[source].format(**format_arguments)

        # make a work directory
        result = execute_and_log_container(f'mkdir -p /{extension[name]}', container, container_log)

        if result.exit_code != 0:
            print(f'[ERROR] make workdir for extension({extension[name]}) is failed.\n{result.output.decode()}')
            continue

        # download build source file
        result = execute_and_log_container(f'curl -L -s -O {build_source_url}', container, container_log, f'/{extension[name]}')

        if result.exit_code != 0:
            print(f'[ERROR] download source for extension({extension[name]}) is failed.\n{result.output.decode()}')
            continue

        extract_command = None

        # extract build source
        result = execute_and_log_container('sh -c "[ -f *.zip ]"', container, container_log, f'/{extension[name]}')
        if result.exit_code == 0:
            extract_command = 'unzip -o *.zip'

        result = execute_and_log_container('sh -c "[ -f *.tar ]"', container, container_log, f'/{extension[name]}')
        if result.exit_code == 0:
            extract_command = 'tar -xvf *.tar'

        result = execute_and_log_container('sh -c "[ -f *.gz ]"', container, container_log, f'/{extension[name]}')
        if result.exit_code == 0:
            extract_command = 'tar -xvzf *.tar'

        if extract_command is not None:
            result = execute_and_log_container(extract_command, container, container_log, f'/{extension[name]}')

        if extract_command is None or result.exit_code!=0:
            print(f'[ERROR] extract source for extension({extension[name]}) is failed.\n{result.output.decode()}')
            continue

        # get an absolute path of Makefile of this extension build source
        result = execute_and_log_container('sh -c "realpath $(dirname $(find -type f -name Makefile | head -n 1))"', container, container_log, f'/{extension[name]}')

        if result.exit_code != 0:
            print(f'[ERROR] there is no Makefile for source of extension({extension[name]})')
            continue

        build_dir = result.output.decode().strip()
        build_command = extension[build].format(**format_arguments)

        # execute make command for build
        result = execute_and_log_container(f'bash --login -c "{build_command}"', container, container_log, build_dir)

        if result.exit_code != 0:
            print(f'[ERROR] build {extension[name]} is failed.\n{result.output.decode()}')
            continue

        prebuilt_package_name = f'{extension[name]}-{extension[version]}-{spec[os][name]}{spec[os][version].split('.')[0]}-pg{spec[database][version].split('.')[0]}.tar'

        # create 'make install' arguments description
        install_command = build_command.replace('make', 'make install', 1)
        result = execute_and_log_container(f'sh -c "echo \'{install_command}\' >> install"', container, container_log, build_dir)

        # packaging
        result = execute_and_log_container(f'tar -cvf {prebuilt_package_name} .', container, container_log, build_dir)

        if result.exit_code != 0:
            print(f'[ERROR] packaging {extension[name]} is failed.\n{result.output.decocde()}')
            continue

        # upload
        json_token = '{' + f'\\\"message\\\": \\\"feat: {extension[name]} {extension[version]} for {spec[os][name]}{spec[os][version].split('.')[0]}, pg{spec[database][version].split('.')[0]}\\\",\\\"content\\\":\\\"'
        execute_and_log_container(f'sh -c "echo \'{json_token}\' >> upload.json"', container, container_log, build_dir)
        execute_and_log_container(f'sh -c "base64 --wrap=0 {prebuilt_package_name} >> upload.json"', container, container_log, build_dir)
        execute_and_log_container('sh -c "echo \'\\\"}\' >> upload.json"', container, container_log, build_dir)

        upload_command_arguments = {
            'upload_access_token': upload_access_token,
            'upload_file_path': f'{extension[name]}/{extension[version]}/{prebuilt_package_name}',
            'upload_json_path': f'{build_dir}/upload.json'
        }

        upload_command = metadata['upload_command'].format(**upload_command_arguments)

        result = execute_and_log_container(upload_command, container, container_log)

        if result.exit_code != 0:
            print(f'[ERROR] uploading {extension[name]} is failed.\n{result.output.decode()}')
            continue

        response = json.loads(result.output.decode().strip())

        if 'content' not in response:
            print(f'[ERROR] uploading {extension[name]} is failed.\n{response}')
            continue

        print(f'[INFO] {extension[name]} {extension[version]} build and upload done...')

if __name__ == '__main__':
    main()
