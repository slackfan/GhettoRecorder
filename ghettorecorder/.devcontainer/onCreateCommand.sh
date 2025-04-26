#!/bin/sh

cd /GhettoRecorder
chmod -R o+rw .

apk update
apk upgrade --update-cache --available
apk add --update --no-cache bash git py3-pip
