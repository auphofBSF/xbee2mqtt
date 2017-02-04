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
            virtualenv $FOLDER --python=python2.7
        fi

        $PIP install --upgrade ConfigParser
        $PIP install --upgrade pyaml
        $PIP install --upgrade pyserial
        $PIP install --upgrade nose
        $PIP install --upgrade paho-mqtt
		$PIP install --upgrade parse
		$PIP install --upgrade xbee
        ;;

    "start" | "stop" | "restart")
        $PYTHON xbee2mqtt.py $ACTION
        ;;

    "tests")
        $PYTHON $FOLDER/bin/nosetests --nocapture
        ;;

    "console")
        $PYTHON xbee2console.py
        ;;

    *)
        echo "Unknown action $ACTION."
        ;;
esac


