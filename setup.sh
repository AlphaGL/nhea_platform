#!/bin/bash

# install dependancies
pip install setuptools
pip install -r requirements.txt

# Run django commands
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic