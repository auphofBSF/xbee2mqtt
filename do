#!/bin/bash

set -e

FOLDER=$(dirname $(realpath $0))/.venv
PIP=$FOLDER/bin/pip
PYTHON=$FOLDER/bin/python

if [ $# -eq 0 ]; then
    ACTION='activate'
else
    ACTION=$1
fi

case "$ACTION" in

    "setup")
        if [ ! -d $FOLDER ]; then
            virtualenv $FOLDER
        fi

        $PIP install --upgrade ConfigParser
        $PIP install --upgrade pyaml
        $PIP install --upgrade pyserial
        $PIP install --upgrade nose
        $PIP install --upgrade paho-mqtt

        TMPDIR=$(mktemp -d)
        wget https://storage.googleapis.com/google-code-archive-source/v2/code.google.com/xoseperez-python-xbee/source-archive.zip \
            -O $TMPDIR/xoseperez-python-xbee.zip
        unzip $TMPDIR/xoseperez-python-xbee.zip -d $TMPDIR

        cd $TMPDIR/xoseperez-python-xbee/
        $PYTHON setup.py install
        cd -
        ;;

    "start" | "stop" | "restart")
        $PYTHON xbee2mqtt.py $ACTION
        ;;

    "tests")
        $PYTHON $FOLDER/bin/nosetests
        ;;

    "console")
        $PYTHON xbee2console.py
        ;;

    *)
        echo "Unknown action $ACTION."
        ;;
esac


