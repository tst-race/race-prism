#!/bin/bash

if ! [ -f venv/bin/activate ]; then
	python3 -m venv venv
	source venv/bin/activate
	pip install -r requirements.txt
	pip install -e .
	pip install -e rib
else
	source venv/bin/activate
fi


cmd='prt build --android -v --ci-run'
echo executing $cmd
$cmd
rm -rf kit
cp -r rib/release ./kit
