#!/bin/bash

cd /opt/primabase
source venv/bin/activate
source .env
flask telegram send
