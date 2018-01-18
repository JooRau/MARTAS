from __future__ import print_function
from __future__ import absolute_import

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

#import sys, time, os
#import binascii, csv


## POS1 protocol
## -------------

class POS1Protocol(LineReceiver):
    """
    Protocol to read POS1 data
    This protocol defines the individual sensor related read process. 
    It is used to dipatch url links containing specific data.
    Sensor specific coding is contained in method "processData".
    """
    def __init__(self, client, sensordict, confdict):
        """
        'client' could be used to switch between different publishing protocols
                 (e.g. MQTT or WS-MCU gateway factory) to publish events
        'sensordict' contains a dictionary with all sensor relevant data (sensors.cfg)
        'confdict' contains a dictionary with general configuration parameters (martas.cfg)
        """
        print ("Begin Initialization of POS1")
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

        delimiter = '\x00'
        self.buffer = ''
        self.ntp_gps_offset = 6.2 # sec
        print ("End Initialization of POS1")

    def connectionMade(self):
        log.msg('  -> {} connected.'.format(self.sensor))

    def connectionLost(self, reason):
        log.msg('  -> {} lost.'.format(self.sensor))

    def processPos1Data(self, data):
        """Convert raw ADC counts into SI units as per datasheets"""
        if len(data) != 44:
            log.err('POS1 - Protocol: Unable to parse data of length %i' % len(data))

        currenttime = datetime.utcnow()
        outdate = datetime.strftime(currenttime, "%Y-%m-%d")
        actualtime = datetime.strftime(currenttime, "%Y-%m-%dT%H:%M:%S.%f")
        outtime = datetime.strftime(currenttime, "%H:%M:%S")
        timestamp = datetime.strftime(currenttime, "%Y-%m-%d %H:%M:%S.%f")
        filename = outdate
        sensorid = self.sensor

        packcode = '6hLLLh6hL'
        header = "# MagPyBin %s %s %s %s %s %s %d" % (self.sensor, '[f,df,var1,sectime]', '[f,df,var1,GPStime]', '[nT,nT,none,none]', '[1000,1000,1,1]', packcode, struct.calcsize('<'+packcode))

        try:
            # Extract data
            data_array = data.split()
            intensity = float(data_array[0])/1000.
            sigma_int = float(data_array[2])/1000.
            err_code = int(data_array[3].strip('[').strip(']'))
            dataelements = datetime.strptime(data_array[4],"%m-%d-%y")
            newdate = datetime.strftime(dataelements,"%Y-%m-%d")
            gps_time = newdate + ' ' + str(data_array[5])[:11]
        except:
            log.err('POS1 - Protocol: Data formatting error.')
            intensity = 0.0
            sigma_int = 0.0
            err_code = 0.0

        try:
            # Analyze time difference between POS1 internal time and utc from PC
            # Please note that the time difference between POS1-GPS (data recorded) 
            # and NTP (data received at PC) can be very large
            # for our POS1 it is 6.2 seconds

            gpstime = datetime.strptime(gps_time, "%Y-%m-%d %H:%M:%S.%f")
            timelist = sorted([gpstime,currenttime])
            timediff = timelist[1]-timelist[0]
            secdiff = timediff.seconds + timediff.microseconds/1E6
            timethreshold = 3
            if secdiff-self.ntp_gps_offset > timethreshold:
                self.errorcnt['time'] +=1
                if self.errorcnt.get('time') < 2:
                    log.msg("{} protocol: large time difference observed for {}: {} sec".format(self.sensordict.get('protocol'), sensorid, secdiff))
                    log.msg("{} protocol: switching to NTP time until timediff is smaller then 3 seconds.".format(self.sensordict.get('protocol')))
                internal_time = timestamp
            else:
                self.errorcnt['time'] = 0 
        except:
            pass


        try:
            # extract time data
            datearray = acs.timeToArray(timestamp)
            gpsarray = acs.timeToArray(gps_time)
            try:
                datearray.append(int(intensity*1000))
                datearray.append(int(sigma_int*1000))
                datearray.append(err_code)
                datearray.extend(gpsarray)
                data_bin = struct.pack('<'+packcode,datearray[0],datearray[1],datearray[2],datearray[3],datearray[4],datearray[5],datearray[6],datearray[7],datearray[8],datearray[9],datearray[10],datearray[11],datearray[12],datearray[13],datearray[14],datearray[15],datearray[16])
            except:
                log.msg('POS1 - Protocol: Error while packing binary data')
                pass
            if not self.confdict.get('bufferdirectory','') == '':
                acs.dataToFile(self.confdict.get('bufferdirectory'), sensorid, filename, data_bin, header)
        except:
            log.msg('POS1 - Protocol: Error with binary save routine')
            pass

        return ','.join(list(map(str,datearray))), header
         

    def dataReceived(self, data):

        topic = self.confdict.get('station') + '/' + self.sensordict.get('sensorid')
        # extract only ascii characters 

        ok = False
        try:
            if len(self.buffer) == 44:
                dataarray, head = self.processPos1Data(self.buffer[:44])
                self.buffer = ''
                try:
                    value = float(dataarray.split(',')[7])
                except:
                    value = 0.0
                if value > 0:
                    ok = True
                else:
                    log.err('POS1 - Protocol: Zero value, skipping. (Value still written to file.)')
            self.buffer = self.buffer + data
            if len(self.buffer) > 44:
                log.msg('POS1 - Protocol: Warning: Bufferlength (%s) exceeds 44 characters, fixing...' % len(self.buffer))
                if repr(data).endswith("x00'"):    # check if last part read is end of POS string.
                    datatest = (len(self.buffer))%44
                    # OPTION 1: Data is good, but too much arrived at once. Split and process.
                    if datatest == 0:
                        dataparts = int(len(self.buffer)/44)
                        log.msg('POS1 - Protocol: It appears multiple parts came in at once, # of parts:', dataparts)
                        for i in range(dataparts):
                            split_data_string = self.buffer[i*44:(i*44)+44]
                            log.msg('POS1 - Protocol: Processing data part # %s in string (%s)' % (str(i+1), split_data_string))
                            dataarray, head = self.processPos1Data(split_data_string)
                            try:
                                value = float(dataarray.split(',')[7])
                            except:
                                value = 0.0
                            if value > 0:
                                ok = True
                            else:
                                log.err('POS1 - Protocol: Zero value, skipping. (Value still written to file.)')
                        self.buffer = ''
                    # OPTION 2: Data is bad; bit was lost.
                    else:
                        log.msg('POS1 - Protocol: String contains bad data. Deleting. (String content: %s)' % self.buffer)
                        self.buffer = ''              # If true, bad data. Log and delete.
                else:    # if last part read is not end of POS string, continue reading.
                    log.msg('POS1 - Protocol: Attempting to fix buffer... last part read:', self.buffer[-10:], "Bufferlength:", len(self.buffer))
        except:
            print('{}: Data seems not be POS1Data: Looks like {}'.format(self.sensordict.get('protocol'),data))
            ok = False


        if ok:
            senddata = False
            coll = int(self.sensordict.get('stack'))
            if coll > 1:
                self.metacnt = 1 # send meta data with every block
                if self.datacnt < coll:
                    self.datalst.append(dataarray)
                    self.datacnt += 1
                else:
                    senddata = True
                    dataarray = ';'.join(self.datalst)
                    self.datalst = []
                    self.datacnt = 0
            else:
                senddata = True

            if senddata:
                self.client.publish(topic+"/data", dataarray)
                if self.count == 0:
                    self.client.publish(topic+"/meta", head)
                self.count += 1
                if self.count >= self.metacnt:
                    self.count = 0

