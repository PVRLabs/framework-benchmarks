"""Load the benchmark JVM configuration."""
import hashlib
import json
from pathlib import Path, PurePosixPath

DEFAULT_PATH = Path(__file__).resolve().parents[1]/'config-v2.json'
STANDARD = dict(java_executable='/opt/boot27/bin/java', jdk_build='27+35-2325',
                jvm=['-Xms16m', '-Xmx80m', '-XX:+UseG1GC', '-Duser.timezone=UTC'])


def validate(settings):
    if not isinstance(settings, dict) or settings.keys() != STANDARD.keys():
        raise ValueError('Configuration must contain exactly: ' + ', '.join(sorted(STANDARD)))
    java = settings['java_executable']
    if not isinstance(java, str) or not PurePosixPath(java).is_absolute() or '\0' in java:
        raise ValueError('java_executable must be an absolute guest path')
    build = settings['jdk_build']
    if not isinstance(build, str) or not build or any(c.isspace() for c in build):
        raise ValueError('jdk_build must be the expected Java build identifier')
    flags = settings['jvm']
    if not isinstance(flags, list) or any(
        not isinstance(flag, str) or len(flag) <= 2 or '\0' in flag
        or not flag.startswith(('-X', '-D')) for flag in flags
    ):
        raise ValueError('jvm must be an array of -X, -XX or -D arguments')
    return settings


def load(path=None):
    path = DEFAULT_PATH if path is None else path
    try:
        return validate(json.loads(path.read_text()))
    except (OSError, ValueError) as exc:
        raise ValueError(f'{path}: {exc}') from exc


def sha256(config):
    encoded = json.dumps(config, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
