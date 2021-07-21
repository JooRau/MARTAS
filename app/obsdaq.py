#!/usr/bin/env python
"""
a script to communicate with ObsDAQ assuming:
    connected to a PalmAcq
    PalmAcq is in Transparent mode (see manual)
    supported only baud rate 57600
"""
from __future__ import print_function
import sys, os, socket, getopt
import serial
import struct, binascii, re, csv
from datetime import datetime, timedelta
from matplotlib.dates import date2num, num2date
import numpy as np
import time

# Relative import of core methods as long as martas is not configured as package
scriptpath = os.path.dirname(os.path.realpath(__file__))
coredir = os.path.abspath(os.path.join(scriptpath, '..', 'core'))
sys.path.insert(0, coredir)
from acquisitionsupport import GetConf2 as GetConf2

# path of config file
#obsdaqconf=""
obsdaqconfpath="/home/pi/MARTAS/conf/obsdaq.cfg"

# settings for PalmDaq
port = '/dev/ttyUSB0'
baudrate='57600'
eol = '\r'


# settings for ObsDAQ:

#   baudrate 19200 is the default after power on
#   test e.g. by minicom after plugged in

# default clock frequency. There'll be a warning if it is different
    #   98 .. 9.8304MHz
FCLK = '98'

# set 24-bit channel configuration
    # assuming crystal frequency is 9.8304MHz
    # command  $AAnWS0201ccdd 
    # cc ... Range mode (gain)
    #   02 ...  +/-10V
    #   03 ...  +/-5V
    #   04 ...  +/-2.5V
CC = '02'
    # dd ... Data output rate (here examples, see Table 6 and Table 9)
    #   03 .. 3.2 Hz
    #   13 .. 6.4 Hz
    #   23 .. 12.8 Hz
    #   33 .. 19.2 Hz
    #   43 .. 32.0 Hz
    #   53 .. 38.4 Hz
    #   63 .. 64 Hz
DD = '23'
#DD = '63'

# setting internal trigger timing
    # command $AAPPeeeeffff
    # eeee ... triggering interval
    # ffff ... low-level time
EEEE = '3C00'
FFFF = '0600'
#EEEE = '0BFF'
#FFFF = '026D'

# program offset calibration constants
    # command $AAnWOaaaaaa
#OFFSET = ['','','']
OFFSET = ['FFF19A','FFF41B','FFF70C']

# program full-scale calibration constants
    # command $AAnWFffffff
#FULLSCALE = ['','','']
FULLSCALE = ['3231C0','32374B','323A7E']

# ----------------------------------
# please don't edit beyond this line
# ----------------------------------

# get constants from config file

if not obsdaqconfpath=="":
    conf = GetConf2(obsdaqconfpath)
    CC = str(conf.get('CC')).zfill(2)
    DD = str(conf.get('DD')).zfill(2)
    EEEE = str(conf.get('EEEE')).zfill(4)
    FFFF = str(conf.get('FFFF')).zfill(4)
    OFFSET = [conf.get('OFFSETX'),conf.get('OFFSETY'),conf.get('OFFSETZ')]
    FULLSCALE = [conf.get('FULLSCALEX'),conf.get('FULLSCALEY'),conf.get('FULLSCALEZ')]

# some calculations

FCLKdic = {'98':9.8304e6,'92':9.216e6,'76':7.68e6}
fclk = FCLKdic[FCLK]
# factor for trigger timing parameters eeee and ffff
micros = 64./fclk
CCdic = {'02':10.,'03':5.,'04':2.5}
gain = CCdic[CC]
DDdic = {'03':3.2,'13':6.4,'23':12.8,'33':19.2,'43':32.,'53':38.4,'63':64.,'72':76.8,'82':128.,'92':640.,'A1':1280.}
# data output rate
drate = DDdic[DD] * FCLKdic[FCLK] / FCLKdic['98']
eeee = int('0x'+EEEE,16)*micros
ffff = int('0x'+FFFF,16)*micros

global QUIET
QUIET = False

def lineread(ser,eol):
            # FUNCTION 'LINEREAD'
            # Does the same as readline(), but does not require a standard 
            # linebreak character ('\r' in hex) to know when a line ends.
            # Variable 'eol' determines the end-of-line char: '\x00'
            # for the POS-1 magnetometer, '\r' for the envir. sensor.
            # (Note: required for POS-1 because readline() cannot detect    
            # a linebreak and reads a never-ending line.)
            ser_str = ''
            timeout = time.time()+2
            while True:
                char = ser.read()
                if char == eol:
                    break
                if time.time() > timeout:
                    print ('Timeout')
                    break
                ser_str += char
            return ser_str

def send_command(ser,command,eol,hex=False):
    #command = eol+command+eol
    command = command+eol
    #print 'Command:  %s \n ' % command.replace(eol,'')
    sendtime = date2num(datetime.utcnow())
    #print "Sending"
    ser.write(command)
    #print "Received something - interpretation"
    response = lineread(ser,eol)
    #print "interprete"
    receivetime = date2num(datetime.utcnow())
    meantime = np.mean([receivetime,sendtime])
    #print "Timediff", (receivetime-sendtime)*3600*24
    return response, num2date(meantime).replace(tzinfo=None)

ser = serial.Serial(port, baudrate=baudrate , parity='N', bytesize=8, stopbits=1, timeout=2)

def command(call):
    global QUIET
    if not QUIET:
        print(call)
    answer, actime = send_command(ser,call,eol)
    if not QUIET:
        print(answer)
    return answer


def main(argv):
    try:
        opts, args = getopt.getopt(argv,"hvcn:f:apsodiq",[])
    except getopt.GetoptError:
        print ('unknown option')
        sys.exit(2)
    import time
    for opt, arg in opts:
        if opt == '-h':
            print ('-------------------------------------')
            print ('Description:')
            print ('Sending data to ObsDAQ via PalmAcq')
            print ('  therefore it is necessary to bring PalmAcq in Transparent mode')
            print ('  i.e. by using the palmacq.py script:')
            print ('  python palmacq.py -t')
            print ('-------------------------------------')
            print ('Usage:')
            print ('obsdaq.py -q -v -c -n channel -f channel -a -p -s -o -d -i')
            print ('-------------------------------------')
            print ('Options:')
            print ('-v          : show version of ObsDAQ and quit')
            print ('')
            print ('-c          : define calibration constants')
            print ('-n channel  : perform an offset system calibration (input must be 0) of channel 1-3')
            print ('-f channel  : perform a full-scale calibration (input must be maximum) of channel 1-3')
            print ('')
            print ('-a          : start acquisition (calibrate first!)')
            print ("-p          : exit free run or triggered mode - stop acquisition")
            print ('-s          : show output from serial line')
            print ('-o          : show the formatted output')
            print ('')
            print ('-d          : show definitions made in this file')
            print ('-i          : show info about ObsDAQ settings')
            print ("-q          : quiet: don't show commands and answers. Has to be first option.")
            print ('-------------------------------------')
            print ('Examples:')
            print ('python obsdaq.py -t')
            sys.exit()
        if opt in ("-v", "--version"):
            answer = ser.read(10)
            if answer:
                print ('ObsDaq: it seems, that acquisition is in progress.')
                print ('ObsDaq: please stop acquisition using -p or --stop option first!')
                exit(2)
            print ('ObsDaq: Firmware version and firmware date')
            command('$01F')
            print ('ObsDaq: Module name (firmware version)')
            command('$01M')
        if opt in ("-q", "--quiet"):
            global QUIET
            QUIET = True
        elif opt in ("-p", "--stop"):
            # stop acquisition
            print('ObsDaq: trying to stop acquisition...')
            command('#01ST')
            stopped = False
            while not stopped:
                # quick stop
                answer, time = send_command(ser,'||||||||||||||||||||||','')
                if answer:
                    print ('Answer from ObsDAQ:')
                    print (answer)
                    print ('ObsDaq: please wait!')
                    for i in range(100):
                        ser.write('|||||||||||||||||||||||||||||||||||\r')
                else:
                    print ('ObsDaq: stopped')
                    stopped = True    
            # stop free run or triggered mode, enter idle mode
            command('#01ST')
        elif opt in ("-i", "--info"):
            answer = ser.read(10)
            if answer:
                print ('ObsDaq: it seems, that acquisition is in progress.')
                print ('ObsDaq: please stop acquisition using -p or --stop option first!')
                exit(2)
            print ('Information - please refer to ObsDAQ manual')
            print ('Serial number')
            sn = command('$01SN')
            sn = sn.split('SN')[1]
            print ('S/N: '+sn)
            # turn off triggering to enable getting 24 bit configuration
            print ('turning off triggering')
            command('#01PP00000000')
            # wait a second
            time.sleep(1)
            print ('baud rate code')
            command('$012')
            print ('quarz frequency')
            ans = command('$01QF')
            ans = ans.split('R')[1]
            if not ans == FCLK:
                print ('WARNING: this code is not written for this crystal frequency.')
                print ('   please adopt python code!')
                print ('')
            print ('first EEPROM command')
            print ('  *ERR indicates there is no EEPROM programmed for autostart')
            command('$01IR0')
            print ('24bit channel 0 config') 
            command('$010RS')
            print ('24bit channel 1 config')
            command('$011RS')
            print ('24bit channel 2 config') 
            command('$012RS')
            
            # get 24-bit channel configuration
            print ('channel configuration')
            command('$010RS')
            command('$011RS')
            command('$012RS')
            time.sleep(1)

            # get offset calibration constants
            print ('offset calibration constants')
            command('$010RO')
            command('$011RO')
            command('$012RO')

            # get full-scale calibration constants
            print ('full scale calibration constants')
            command('$010RF')
            command('$011RF')
            command('$012RF')

        elif opt in ("-s", "--show"):
            while True:
                print (lineread(ser,eol))

        elif opt in ("-c", "--calib"):
            answer = ser.read(10)
            if answer:
                print ('ObsDaq: it seems, that acquisition is in progress.')
                print ('ObsDaq: please stop acquisition using -p or --stop option first!')
                exit(2)

            print ('ObsDaq: turning off triggering')
            command('#01PP00000000')
            # wait a second
            time.sleep(1)

            print ('ObsDaq: setting 24-bit channel configuration')
            # cc=02..+/-10V
            # dd=23..12.8Hz
            command('$010WS0201'+CC+DD)
            time.sleep(1)
            command('$011WS0201'+CC+DD)
            time.sleep(1)
            command('$012WS0201'+CC+DD)
            time.sleep(1)

            # calibration constants
            for i in range(3):
                if OFFSET[i]:
                    print ('programming given offset calibration constant for channel '+str(i+1))
                    command('$01'+str(i)+'WO'+OFFSET[i])
            for i in range(3):
                if FULLSCALE[i]:
                    print ('programming given full-scale calibration constant for channel '+str(i+1))
                    command('$01'+str(i)+'WF'+FULLSCALE[i])
            time.sleep(1)
            # execute an offset and full-scale self-calibration if necessary
            for i in range(3):
                if not OFFSET[i] or not FULLSCALE[i]:
                    print ('executing an offset and full-scale self-calibration for channel '+str(i+1))
                    command('$01'+str(i)+'WCF0')
                    print ('calibrating...')
                    # check calibration finished?
                    calfin = False
                    while not calfin:
                        time.sleep(0.5)
                        ans = command('$01'+str(i)+'RR')
                        ans = ans.split('R')[1]
                        if ans == '0':
                            print ('ObsDaq: finished calibration')
                            calfin = True
            
            # get 24-bit channel configuration
            print ('channel configuration')
            a=command('$010RS')
            b=command('$011RS')
            c=command('$012RS')
            if QUIET:
                print('\t'+a+'\t'+b+'\t'+c)
                accdd='\t+/-'+str(CCdic[a[7:9]])+'V  '+str(DDdic[a[9:11]])+'Hz'
                bccdd='\t+/-'+str(CCdic[b[7:9]])+'V  '+str(DDdic[b[9:11]])+'Hz'
                cccdd='\t+/-'+str(CCdic[c[7:9]])+'V  '+str(DDdic[c[9:11]])+'Hz'
                print(accdd+'\t'+bccdd+'\t'+cccdd)
            time.sleep(1)

            # get offset calibration constants
            print ('offset calibration constants')
            a=command('$010RO')
            b=command('$011RO')
            c=command('$012RO')
            if QUIET:
                print('\t'+a+'\t'+b+'\t'+c)

            # get full-scale calibration constants
            print ('full scale calibration constants')
            a=command('$010RF')
            b=command('$011RF')
            c=command('$012RF')
            if QUIET:
                print('\t'+a+'\t'+b+'\t'+c)

        elif opt in ("-n", "--offsetcal"):
            try:
                ch = int(arg)-1
                ch = str(ch)
            except:
                print ("channel must be in 1..3")
                exit(2)
            answer = ser.read(10)
            if answer:
                print ('it seems, that acquisition is in progress.')
                print ('please stop acquisition using -p or --stop option first!')
                exit(2)
            
            print ('turning off triggering')
            command('#01PP00000000')
            # wait a second
            time.sleep(1)

            print ('setting 24-bit channel configuration')
            # cc=02..+/-10V
            # dd=23..12.8Hz
            command('$01'+ch+'WS0201'+CC+DD)
            time.sleep(1)

            print ('performing offset calibration of channel '+arg)
            command('$01'+ch+'WCF3')
            time.sleep(1)
            print ('get the constants from python obsdac.py -i')

        elif opt in ("-f", "--fullscalecal"):
            try:
                ch = int(arg)-1
                ch = str(ch)
            except:
                print ("channel must be in 1..3")
                exit(2)
            answer = ser.read(10)
            if answer:
                print ('it seems, that acquisition is in progress.')
                print ('please stop acquisition using -p or --stop option first!')
                exit(2)
            
            print ('turning off triggering')
            command('#01PP00000000')
            # wait a second
            time.sleep(1)

            print ('setting 24-bit channel configuration')
            # cc=02..+/-10V
            # dd=23..12.8Hz
            command('$010WS0201'+CC+DD)
            time.sleep(1)
            command('$011WS0201'+CC+DD)
            time.sleep(1)
            command('$012WS0201'+CC+DD)
            time.sleep(1)

            print ('performing full-scale calibration of channel '+arg)
            command('$01'+ch+'WCF4')
            time.sleep(1)
            print ('get the constants from python obsdac.py -i')



        elif opt in ("-d", "--defs"):
            # show user settings human readable
            print ("Definitions for ObsDAQ made in this file:")
            print ('')
            print ('Clock frequency:')
            print ('FCLK:\t'+FCLK)
            print ('\t'+str(fclk/1000000.)+'MHz')
            print ('Gain:')
            print ('CC:\t'+CC)
            print ('\t+/-'+str(gain)+'V')
            print ('Data output rate:')
            print ('DD:\t'+DD)
            print ('\t'+str(1./drate)+" s")
            print ('\t'+str(drate)+' Hz')
            print ('triggering interval')
            print ('EEEE:\t'+EEEE)
            print ('\t'+str(eeee)+" s")
            print ('\t'+str(1./eeee)+" Hz")
            print ('low-level time')
            print ('FFFF:\t'+FFFF)
            print ('\t'+str(ffff)+" s")
            print ('\t'+str(1./ffff)+" Hz")
            # there are limitations in choosing DD, EEEE and FFFF:
            if drate < 1./eeee:
                print ('WARNING: Digital filter output rate is smaller than the triggering frequency!')
                print ('drate '+str(drate)+'Hz < 1./eeee '+str(1./eeee)+'Hz')
            if 1./drate - 0.0011 > eeee:
                print ('WARNING: The difference of triggering interval and digital filter interval is smaller than 1.1ms!')
                print ('1./drate '+str(1./drate)+'s - 0.0011s > eeee '+str(eeee)+'s')
            if eeee - ffff < 0.00019:
                print ('WARNING: Difference between triggering interval and low-level time is '+str(eeee-ffff)+'!')
            if eeee - ffff < 1./drate:
                print ('WARNING: Triggering interval - Low-level time is higher than the Digital filter output rate!')

        elif opt in ("-a", "--start"):
            print ('ObsDaq: starting acquisition')
            # set internal trigger timing (Table 9)
            command('#01PP'+EEEE+FFFF)
            # wait a second
            time.sleep(2)

            # start acquisition (plus supplementary data every second)
            command('#01CS')
            
            time.sleep(2)



if __name__ == "__main__":
    main(sys.argv[1:])
            






    
