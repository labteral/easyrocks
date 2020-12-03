#!/bin/bash
source env.sh
docker push labteral/easyrocks:$VERSION
docker push labteral/easyrocks:latest
