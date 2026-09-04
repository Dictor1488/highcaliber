# -*- coding: utf-8 -*-
from __future__ import print_function
import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rm(path):
    path = Path(path)
    if path.is_dir():
        shutil.rmtree(str(path))
    elif path.exists():
        path.unlink()


def copytree(src, dst):
    src = Path(src)
    dst = Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for name in os.listdir(str(src)):
        if name == '.gitkeep':
            continue
        source = src / name
        target = dst / name
        if source.is_dir():
            copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(target))


def clean_pyc():
    for path in Path('python').rglob('*.pyc'):
        path.unlink()
    for path in Path('python').rglob('__pycache__'):
        if path.is_dir():
            shutil.rmtree(str(path))


def compile_python():
    files = [str(path).replace('\\', '/') for path in Path('python').rglob('*.py')]
    if not files:
        return
    clean_pyc()
    py27 = os.environ.get('PYTHON27')
    if py27:
        subprocess.check_call([py27, '-m', 'py_compile'] + files)
        return
    if sys.platform.startswith('win') and Path('C:/Python27/python.exe').exists():
        subprocess.check_call(['C:/Python27/python.exe', '-m', 'py_compile'] + files)
        return
    for candidate in ('python2.7', 'python2'):
        try:
            subprocess.check_call([candidate, '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.check_call([candidate, '-m', 'py_compile'] + files)
            return
        except Exception:
            pass
    subprocess.check_call([
        'docker', 'run', '--rm',
        '-v', '{}:/work'.format(str(ROOT).replace('\\', '/')),
        '-w', '/work',
        'python:2.7', 'python', '-m', 'py_compile'
    ] + files)


def copy_compiled_python(src, dst):
    for path in Path(src).rglob('*.pyc'):
        target = Path(dst) / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(target))


def write_meta(temp, info):
    root = ET.Element('root')
    for key in ('id', 'version', 'name', 'description'):
        ET.SubElement(root, key).text = str(info.get(key, ''))
    try:
        ET.indent(root, space='    ')
    except Exception:
        pass
    (Path(temp) / 'meta.xml').write_text(ET.tostring(root, encoding='unicode'), encoding='utf-8')


def zip_stored(source, destination):
    with zipfile.ZipFile(str(destination), 'w', compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(Path(source).rglob('*')):
            if path.is_dir():
                continue
            arc = str(path.relative_to(source)).replace('\\', '/')
            info = zipfile.ZipInfo(arc)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def main():
    os.chdir(str(ROOT))
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', default=None)
    args = parser.parse_args()

    cfg = json.loads(Path('build.json').read_text(encoding='utf-8'))
    if args.version:
        cfg['info']['version'] = args.version

    temp = Path('temp')
    build = Path('build')
    rm(temp)
    rm(build)
    temp.mkdir(parents=True)
    build.mkdir(parents=True)

    compile_python()
    copytree('resources/in', temp / 'res')
    copy_compiled_python('python', temp / 'res/scripts/client')
    write_meta(temp, cfg['info'])

    output = build / '{}_{}.wotmod'.format(cfg['info']['id'], cfg['info']['version'])
    zip_stored(temp, output)
    print('Created {}'.format(output))

    clean_pyc()
    rm(temp)


if __name__ == '__main__':
    main()
