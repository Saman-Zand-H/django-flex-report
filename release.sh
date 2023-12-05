#!/bin/bash

REPO="testpypi"
[ -n "$1" ] && REPO="pypi"

rm -r build dist *.egg*
python setup.py sdist bdist_wheel
[ -n "$1" ] && twine upload --repository $REPO dist/* || twine upload dist/*
