#!/bin/bash
unset LD_LIBRARY_PATH
unset LD_PRELOAD
unset PYTHONPATH

sleep 15
cd /home/porco/GW2RPC_fork
./venv/bin/python run.py
