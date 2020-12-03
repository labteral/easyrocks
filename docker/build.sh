#!/bin/bash
source env.sh
docker rmi labteral/easyrocks:$VERSION 2> /dev/null
tar cf ../../easyrocks.tar ../
mv ../../easyrocks.tar .
docker build --no-cache -t labteral/easyrocks:$VERSION .
docker tag labteral/easyrocks:$VERSION labteral/easyrocks:latest
rm -f easyrocks.tar