#!/bin/sh

cd /GhettoRecorder

git config --global --add safe.directory .
git config --local core.autocrlf input
git config --local init.templateDir ~/.git-template

python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements_dev.txt
echo go
