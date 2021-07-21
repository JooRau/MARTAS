from __future__ import print_function
from __future__ import absolute_import

"""
Protocol for PalmAcq and ObsDAQ by MINGEO, Hungary

works for ObsDaqs since 55Fxxx serial numbers when connected to a
PalmAcq by a combined port cable
The MARTAS host is connected to PalmAcq by USB cable

Settings are made in a config file defined in martas.cfg like
obsdaqconfpath  :  /etc/martas/obsdaq.cfg

"""


# ###################################################################
# Import packages
# ###################################################################

import re     # for interpretation of lines
import struct # for binary representation
import socket # for hostname identification
import string # for ascii selection
from datetime import datetime, timedelta
from twisted.protocols.basic import LineReceiver
from twisted.python import log
from magpy.acquisition import acquisitionsupport as acs
import serial # for initializing command
import os,sys

# Relative import of core methods as long as martas is not configured as package
scriptpath = os.path.dirname(os.path.realpath(__file__))
coredir = os.path.abspath(os.path.join(scriptpath, '..', 'core'))
sys.path.insert(0, coredir)
from acquisitionsupport import GetConf2 as GetConf2


def datetime2array(t):
    return [t.year,t.month,t.day,t.hour,t.minute,t.second,t.microsecond]


## Mingeo ObsDAQ protocol
##
class obsdaqProtocol(LineReceiver):
    """
    The Obsdaq protocol gets data assuming:
        connected to a PalmAcq
        PalmAcq is in Transparent mode (see manual)

    SETUP:
        1.) use palmacq.py to make settings of PalmAcq 
        2.) use obsdaq.py to make settings of ObsDAQ
    """
    def __init__(self, client, sensordict, confdict):
        """
        'client' could be used to switch between different publishing protocols
                 (e.g. MQTT or WS-MCU gateway factory) to publish events
        'sensordict' contains a dictionary with all sensor relevant data (sensors.cfg)
        'confdict' contains a dictionary with general configuration parameters (martas.cfg)
        """
        self.client = client
        self.sensordict = sensordict    
        self.confdict = confdict
        self.count = 0  ## counter for sending header information
        self.sensor = sensordict.get('sensorid')
        self.hostname = socket.gethostname()
        self.printable = set(string.printable)
        #log.msg("  -> Sensor: {}".format(self.sensor))
        self.datalst = []
        self.datacnt = 0
        self.metacnt = 10
        self.errorcnt = {'time':0}

        self.delaylist = []  # delaylist contains up to 1000 diffs between gps and ntp
                             # the median of this values is used for ntp timedelay
        self.timedelay = 0.0
        self.timethreshold = 3 # secs - waring if timedifference is larger the 3 seconds

        # Serial configuration
        self.baudrate=int(sensordict.get('baudrate'))
        self.port = confdict['serialport']+sensordict.get('port')
        self.parity=sensordict.get('parity')
        self.bytesize=int(sensordict.get('bytesize'))
        self.stopbits=int(sensordict.get('stopbits'))
        self.delimiter='\r'
        self.timeout=2 # should be rate dependend


        # QOS
        self.qos=int(confdict.get('mqttqos',0))
        if not self.qos in [0,1,2]:
            self.qos = 0
        log.msg("  -> setting QOS:", self.qos)

        # Debug mode
        debugtest = confdict.get('debug')
        self.debug = False
        if debugtest == 'True':
            log.msg('DEBUG - {}: Debug mode activated.'.format(self.sensordict.get('protocol')))
            self.debug = True    # prints many test messages
        else:
            log.msg('  -> Debug mode = {}'.format(debugtest))

        # get obsdaq specific constants
        self.obsdaqconf = GetConf2(self.confdict.get('obsdaqconfpath'))

    def connectionMade(self):
        log.msg('  -> {} connected.'.format(self.sensor))

    def connectionLost(self, reason):
        log.msg('  -> {} lost.'.format(self.sensor))
        log.msg(reason)

    def processData(self, data):
        currenttime = datetime.utcnow()
        outdate = datetime.strftime(currenttime, "%Y-%m-%d")
        filename = outdate
        sensorid = self.sensor
        datearray = []
        dontsavedata = False

        packcode = '6hLlll'
        # int!
        # TODO units, names and factors general 
        header = "# MagPyBin %s %s %s %s %s %s %d" % (self.sensor, '[x,y,z]', '[X,Y,Z]', '[nT,nT,nT]', '[1000,1000,1000]', packcode, struct.calcsize(packcode))
        # TODO finish this
        packcodeSup = '6hL....'
        headerSup = "# MagPyBin %s %s %s %s %s %s %d" % (self.sensor, '[var1,t2,var3,var4,var5]', '[Vcc,Telec,sup1,sup2,sup3]', '[V,degC,V,V,V]', '[1000,1000,1000,1000,1000]', packcode, struct.calcsize(packcode))

        if data.startswith(':R'):
            # :R,00,YYMMDD.hhmmss.sss,*xxxxxxyyyyyyzzzzzzt
            # :R,00,YYMMDD.hhmmss.sss,*xxxxxxyyyyyyzzzzzzt:vvvvttttppppqqqqrrrr
            # :R,00,200131.143739.617,*0259FEFFF1BFFFFCEDL:04AC11CC000B000B000B
            d = data.split(',')
            Y = int('20'+d[2][0:2])
            M = int(d[2][2:4])
            D = int(d[2][4:6])
            h = int(d[2][7:9])
            m = int(d[2][9:11])
            s = int(d[2][11:13])
            us = int(d[2][14:17]) * 1000
            timestamp = datetime(Y,M,D,h,m,s,us)
            if d[3][0] == '*':
                GAINMAX = self.obsdaqconf.get('GAINMAX')
                SCALE_X = self.obsdaqconf.get('SCALE_X')
                SCALE_Y = self.obsdaqconf.get('SCALE_Y')
                SCALE_Z = self.obsdaqconf.get('SCALE_Z')
                x = (int('0x'+d[3][1:7],16) ^ 0x800000) - 0x800000
                x = float(x) * 2**-23 * GAINMAX * SCALE_X
                y = (int('0x'+d[3][7:13],16) ^ 0x800000) - 0x800000
                y = float(y) * 2**-23 * GAINMAX * SCALE_Y
                z = (int('0x'+d[3][13:19],16) ^ 0x800000) - 0x800000
                z = float(z) * 2**-23 * GAINMAX * SCALE_Z
                triggerflag = d[3][19]
            else:
                typ = "none"
            supplement = False
            sup = d[3].split(':')
            if len(sup) == 2:
                supplement = True
                voltage = int(sup[1][0:4],16) ^ 0x8000 - 0x8000
                voltage = float(voltage) * 2.6622e-3 + 9.15
                voltage = round(voltage*1000)/1000.
                temp = int(sup[1][4:8],16) ^ 0x8000 - 0x8000
                temp = float(temp) / 128.
                temp = round(temp*1000)/1000.
                p = (int('0x'+sup[1][8:12],16) ^ 0x8000) - 0x8000
                p = float(p) / 8000.0
                p = int(round(p*1000)/1000)
                q = (int('0x'+sup[1][8:12],16) ^ 0x8000) - 0x8000
                q = float(q) / 8000.0
                q = int(round(q*1000)/1000)
                r = (int('0x'+sup[1][8:12],16) ^ 0x8000) - 0x8000
                r = float(r) / 8000.0
                r = int(round(r*1000)/1000)
            if self.debug:
                log.msg(str(timestamp)+'\t',end='')
                log.msg(str(x)+'\t',end='')
                log.msg(str(y)+'\t',end='')
                log.msg(str(z)+'\t',end='')
                log.msg(str(triggerflag))
                if len(sup) == 2:
                    log.msg('supplementary:\t',end='')
                    log.msg(str(voltage)+' V\t',end='')
                    log.msg(str(temp)+' degC\t',end='')
                    log.msg(str(p)+'\t',end='')
                    log.msg(str(q)+'\t',end='')
                    log.msg(str(r)+'\t')
            typ = "valid"
        else:
            typ = "none"
            if self.debug:
                log.msg(':R not found')
 
        if not typ == "valid": 
            dontsavedata = True

        if not typ == "none":
            datearray = datetime2array(timestamp)
            try:
                # x, y and z have [pT]
                datearray.append(int(round(x)))
                datearray.append(int(round(y)))
                datearray.append(int(round(z)))
                data_bin = struct.pack('<'+packcode,*datearray)
            except:
                log.msg('{} protocol: Error while packing binary data'.format(self.sensordict.get('protocol')))

            if not self.confdict.get('bufferdirectory','') == '':
                acs.dataToFile(self.confdict.get('bufferdirectory'), sensorid, filename, data_bin, header)
            returndata = ','.join(list(map(str,datearray)))
        else:
            returndata = ''

        return returndata, header

         
    def lineReceived(self, line):
        topic = self.confdict.get('station') + '/' + self.sensordict.get('sensorid')
        # extract only ascii characters 
        line = ''.join(filter(lambda x: x in string.printable, line))
        ok = True
        #try:
        if 1:
            data, head = self.processData(line)
        #except:
        else:
            print('{}: Data seems not to be PalmAcq data: Looks like {}'.format(self.sensordict.get('protocol'),line))
            ok = False

        if ok:
            senddata = False
            coll = int(self.sensordict.get('stack'))
            if coll > 1:
                self.metacnt = 1 # send meta data with every block
                if self.datacnt < coll:
                    self.datalst.append(data)
                    self.datacnt += 1
                else:
                    senddata = True
                    data = ';'.join(self.datalst)
                    self.datalst = []
                    self.datacnt = 0
            else:
                senddata = True

            if senddata:
                self.client.publish(topic+"/data", data, qos=self.qos)
                if self.count == 0:
                    add = "SensorID:{},StationID:{},DataPier:{},SensorModule:{},SensorGroup:{},SensorDecription:{},DataTimeProtocol:{}".format( self.sensordict.get('sensorid',''),self.confdict.get('station',''),self.sensordict.get('pierid',''),self.sensordict.get('protocol',''),self.sensordict.get('sensorgroup',''),self.sensordict.get('sensordesc',''),self.sensordict.get('ptime','') )
                    self.client.publish(topic+"/dict", add, qos=self.qos)
                    self.client.publish(topic+"/meta", head, qos=self.qos)
                self.count += 1
                if self.count >= self.metacnt:
                    self.count = 0

