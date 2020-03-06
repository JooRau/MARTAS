#!/bin/sh

MARTASPATH="/home/pi/MARTAS"
APPPATH=$MARTASPATH"/app"

# set PalmAcq into idle mode
python $APPPATH/palmacq.py -p
sleep 2
python $APPPATH/palmacq.py -p
sleep 2
# set PalmAcq into Transparent mode to access ObsDAQ
python $APPPATH/palmacq.py -t
sleep 2
# stop ObsDAQ's acquisition, if running  
python $APPPATH/obsdaq.py -p
sleep 5
python $APPPATH/obsdaq.py -p
sleep 2
# execute a self calibration resp. load calibration values
python $APPPATH/obsdaq.py -c
sleep 2
# start acquisition
python $APPPATH/obsdaq.py -a
sleep 2
# set PalmAcq into idle mode
python $APPPATH/palmacq.py -p
sleep 2
# set PalmAcq into forward mode
python $APPPATH/palmacq.py -d R
sleep 2

