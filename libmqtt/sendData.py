from twisted.python import log

def setDefaults(self, client, sensordict, confdict):
    # TODO to be changed?
    self.qos = 0
    self.debug = False

    self.client = client
    self.sensordict = sensordict
    self.confdict = confdict
    # variables for broadcasting via mqtt:
    self.count=0
    self.datalst = []
    self.datacnt = 0
    self.metacnt = 10
    ###


def sendData(self, sensorid, data, head, stack=None):

    topic = self.confdict.get('station') + '/' + sensorid
    senddata = False
    if not stack:
        stack = int(self.sensordict.get('stack'))
    coll = stack

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
            if self.count == 0:
                # get all values initially from the database
                #add = "SensoriD:{},StationID:{},DataPier:{},SensorModule:{},SensorGroup:{},SensorDecription:{},DataTimeProtocol:{}".format( sensorid, self.confdict.get('station',''),self.sensordict.get('pierid',''), self.sensordict.get('protocol',''),self.sensordict.get('sensorgroup',''),self.sensordict.get('sensordesc',''), self.sensordict.get('ptime','') )
                #self.client.publish(topic+"/dict", add, qos=self.qos)
                self.client.publish(topic+"/meta", head, qos=self.qos)
                if self.debug:
                    log.msg("  -> DEBUG - Publishing meta --", topic, head)
            self.client.publish(topic+"/data", data, qos=self.qos)
            if self.debug:
                log.msg("  -> DEBUG - Publishing data")
            self.count += 1
            if self.count >= self.metacnt:
                self.count = 0

