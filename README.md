# OpenSQL Extensions

- 특정 OS, PG 버전의 환경에서 빌드 자동화 도구 `make`를 이용하여 미리 빌드한 파일을 업로드한 pg extension 빌드 파일 저장소입니다

- [tmax-opensql-packager](https://github.com/tmaxopensql/tmax-opensql-packager)(OpenSQL 설치 패키지 생성 툴)를 통해 특정 os 및 pg 버전 맞춤형 OpenSQL 설치 패키지를 생성할 때, OpenSQL 패키지에 포함시킬 pg extension을 패키지 툴이 매번 직접 빌드하는 반복작업을 생략하기 위해 이 저장소를 활용합니다.  
    OpenSQL 설치 패키지 생성 툴은 패키지 생성 중에 이 저장소에서 PG,OS버전에 맞는 extension 빌드파일을 참조하여 OpenSQL 패키지에 자동으로 포함시킵니다

- extension 파일들은 os, pg의 버전정보에 따라 다음과 같은 규칙을 가진 파일 경로로 저장합니다  
    `{이름}/{버전}/{이름}-{버전}-{OS이름}{OS메이저버전}-pg{PG메이저버전}.tar`

- 각각의 extension tar 파일들은 extension 설치에 필요한 구성파일을 전부 포함하고 있기 때문에, tar 압축 해제 후 `make install` 명령 수행을 통해 현재 환경에 설치된 postgresql 서버에 해당 extension을 추가할 수 있습니다  
    (단, extension tar가 명시하는 os, pg 버전과 환경이 일치해야하며, 설치하고자 하는 서버 환경은 extension 설치에 필요한 도구 `make` 및 `llvm`이 미리 설치되어 있어야 합니다)

- 원하는 os,pg의 버전에 맞게 설정한 extension을 빌드하고, 이 저장소로 업로드하는 자동화 스크립트 도구 builder를 제공합니다.

## Builder 스크립트 사용법

### 요구사항

해당 툴을 사용하기 앞서, 다음 요소들이 툴을 사용하려는 머신에 설치되어 있어야 합니다.

- Python3 + pip (툴 개발은 Python 3.12.3 버전에서 진행되었습니다.)
- docker

### 구성요소

툴은 다음과 같은 구성요소로 이루어져 있습니다.

- `logs` (디렉토리) : 툴 실행 시 사용된 도커 컨테이너 내부 로그를 기록합니다. (툴 실행 시 디렉토리 및 로그파일이 자동 생성됩니다.)
- `input.yaml` : 빌드하려는 extension과 pg, os정보를 설정할 수 있는 파일입니다.
- `builder.yaml` : 툴 수행에 있어 필요한 pg, os등의 메타데이터 정보 모음입니다.  
    (가급적이면 변경하실 필요는 없습니다)
- `builder.py` : 툴 수행동작을 기술한 파이썬 스크립트입니다.
- `requirements.txt` : 툴 사용에 필요한 파이썬 요구 라이브러리 모음입니다.

### 초기 세팅

툴을 사용하려는 환경에서 최초로 한 번 설정해주는 세팅 작업입니다.

#### 파이썬 세팅

다음 명령을 실행하여, 툴 내부에서 필요로 하는 외부 라이브러리 세팅을 진행합니다.

```
pip install -r requirements.txt
```

설치 후 `pip list`를 통해 아래와 같은 라이브러리들이 설치되었는지 확인합니다.

```
$ pip list
Package            Version
------------------ ---------
certifi            2024.8.30
charset-normalizer 3.3.2
docker             7.1.0
idna               3.10
pip                24.0
PyYAML             6.0.2
requests           2.32.3
urllib3            2.2.3
```

#### 토큰 세팅

이 툴은 빌드후 tar 압축한 pg extension 파일을 저장소에 업로드하는 과정이 포함되어 있습니다.  
따라서 파일 업로드 시 access token이 있어야 정상 동작이 가능하기 때문에 환경변수를 통해 토큰 설정을 한번 진행해주어야 합니다

기본적으로 `OPENSQL_EXTENSION_BUILDER_ACCESS_TOKEN`라는 이름의 환경변수를 사용하지만, 필요에 따라 `builder.yaml` 내부의 `upload_token_env_key`을 통해 환경변수 이름을 변경할 수 있습니다.

엑세스토큰은 문의주시면 공유드립니다.

```bash
# linux 기준
echo 'export OPENSQL_EXTENSION_BUILDER_ACCESS_TOKEN={엑세스토큰}' >> ~/.bashrc
source ~/.bashrc
```

### 빌드 세팅

매번 pg extension 빌드 및 업로드 작업 수행 시, `input.yaml` 를 수정하여 extension, os, pg 설정을 변경할 수 있습니다

```yaml
# 빌드 및 설치하려는 os의 종류와 버전
# 현재는 oraclelinux, rockylinux의 8,9버전을 지원합니다
os:
  name: rockylinux
  version: 8.10

# pg extension 을 빌드하려는 pg 버전을 설정합니다
database:
  name: postgresql # 고정치
  version: 15.8

# 빌드 후 업로드하려는 extension들을 나열합니다
# name, version, source, build 모두 필수로 기재해야 합니다
# version: 각 extension의 github release 에서 제시하는 버전정보와 완전 일치해야합니다  
#           (예를들어 2.8.0 버전인데, 2.8 까지만 적으면 안됩니다)
# source: 각 extension의 github release 페이지에서 제공하는 소스파일 url 포맷을 사용합니다
# build: 빌드 시 수행할 명령어 (공통적으로 make를 사용하나 extension에 따라 명령 인자가 조금씩 달라지기 때문에 각 extension 레퍼런스를 참고하여 extension 별로 정확한 빌드 명령어를 기재해야 합니다)
extensions:
  - name: pgaudit
    version: 1.7.0
    source: https://github.com/pgaudit/pgaudit/archive/refs/tags/{version}.zip
    build: make USE_PGXS=1 PG_CONFIG=/usr/pgsql-{db_major_version}/bin/pg_config

  - name: system_stats
    version: 3.2
    source: https://github.com/EnterpriseDB/system_stats/archive/refs/tags/v{version}.zip
    build: make USE_PGXS=1

  - name: credcheck
    version: 2.8.0
    source: https://github.com/MigOpsRepos/credcheck/archive/refs/tags/v{major_version}.{minor_version}.zip
    build: make
```

`input.yaml` 에 입력한 extension 중 이미 해당 저장소에 업로드되어 있어 사용가능하다면, 해당 extension 은 빌드 스킵합니다


### 스크립트 실행

위 input.yaml 설정이 끝나면, 다음과 같이 실행하여 OpenSQL 설치 패키지 생성을 실행합니다.

```
python3 builder.py
```

빌드 및 업로드는 스크립트를 실행하는 환경의 하드웨어 성능에 따라 다르나, extension 3개 빌드 기준 대략 5분 정도의 시간이 소요됩니다.


### (참고) 메타데이터 세팅

```yaml
# 빌드할 수 있는 os 메타 설정
os:
  oraclelinux:
    group: redhat           # group 정보에 따라 pg의 설치 커맨드가 달라집니다
    repository:
      type: docker
      value: oraclelinux
    epel_settings:          # 해당 os의 epel 세팅을 위한 command 를 나열합니다
      common:               # common은 os 버전 상관없이 공통으로 수행하는 명령입니다
        - dnf -y install epel-release
        - dnf config-manager --enable ol{os_major_version}_codeready_builder
  rockylinux:
    group: redhat
    repository:
      type: docker
      value: rockylinux/rockylinux
    epel_settings:          # os major 버전에 따라 epel 세팅 명령이 다른 경우입니다
      "8":
        - dnf -y install epel-release
        - dnf config-manager --set-enabled powertools
      "9":
        - dnf -y install epel-release
        - crb enable
        - dnf config-manager --set-enabled crb
database:
  postgresql:
    install_commands:       # extension 빌드를 위한 pg 및 유틸 설치 커맨드 모음입니다
      redhat:
        - dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-{os_major_version}-x86_64/pgdg-redhat-repo-latest.noarch.rpm
        - dnf -qy module disable postgresql
        - dnf install -y postgresql{db_major_version}-server-{db_version}
        - dnf install -y postgresql{db_major_version}-devel-{db_version}
        - dnf install -y make gcc redhat-rpm-config openssl-devel clang llvm tar findutils unzip
        - sh -c "echo 'export PATH=$PATH:/usr/pgsql-{db_major_version}/bin/' >> ~/.bash_profile"

# 빌드한 extension 파일을 다운로드 받기 위한 url 링크 포맷입니다
# 빌드하려는 extension이 이미 빌드한 적이 있어서 깃헙에 업로드 되어있는지 확인하기 위해 사용됩니다
prebuilt_extension_download_url: https://raw.githubusercontent.com/tmaxopensql/tmax-opensql-extensions/refs/heads/main/{name}/{version}/{name}-{version}-{os_name}{os_major_version}-pg{db_major_version}.tar

# 빌드한 extension 파일을 업로드하기 위한 명령어 포맷입니다
# github api를 통해 파일 업로드를 수행합니다
upload_command: >
  curl -s -L
  -X PUT
  -H "Accept: application/vnd.github+json"
  -H "Authorization: Bearer {upload_access_token}"
  -H "X-GitHub-Api-Version: 2022-11-28"
  https://api.github.com/repos/tmaxopensql/tmax-opensql-extensions/contents/{upload_file_path}
  -d @{upload_json_path}

# 파일 업로드 수행 시 사용될 엑세스 토큰의 값을 저장한 환경변수 이름이 무엇인지 기재합니다
upload_token_env_key: OPENSQL_EXTENSION_BUILDER_ACCESS_TOKEN
```
