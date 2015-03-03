#!/usr/bin/env python
#
# Copyright 2015 British Broadcasting Corporation
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

'''
Wrapper class for detect.py and analyse.py functions to gather measurmeents
from an arduino and analyse them.

'''

import arduino 
import detect
import analyse
import time
import sys

class DubiousInput(Exception):
    
    def __init__(self, value):
        super(DubiousInput, self).__init__(value)


class Measurer:
    
    def __init__(self, pinsToMeasure, expectedTimings, videoStartTicks, wallClock, syncTimelineClock, syncTimelineTickRate):
        """\
        
        connect with the arduino and send commands on which pins are to be read during
        data capture.
        
        :param pinsToMeasure a list of pin names that are to be measured.
                a name must be one of "LIGHT_0", "LIGHT_1", "AUDIO_0" or "AUDIO_1"
        :param expectedTimings  dict mapping pin names ("LIGHT_0","LIGHT_1","AUDIO_0","AUDIO_1") to lists containing expected flash/beep times
        read from a json metadata file. For pins that are not specified as arguments, there will be no entry in the dict.
        :param videoStartTicks initial sync time line clock value
        :param wallClock the wall clock object.  This will be used in arduino.py
                to take various time snapshots
        :param syncTimelineClock the sync time line clock object
        :param syncTimelineTickRate: tick rate of the sync timeline
        """
        
        self.pinsToMeasure = pinsToMeasure
        self.expectedTimings = expectedTimings          
        self.videoStartTicks = videoStartTicks
        self.wallClock = wallClock
        self.syncTimelineClock = syncTimelineClock
        self.syncClockTickRate = syncTimelineTickRate

        self.f = arduino.connect()
        self.pinMap = {"LIGHT_0": 0, "AUDIO_0": 1, "LIGHT_1": 2, "AUDIO_1": 3}
        self.activatePinReading()
        self.nActivePins  = arduino.prepareToCapture(self.f, wallClock)[0]
        
        print self.nActivePins, self.pinsToMeasure
        if self.nActivePins != len(self.pinsToMeasure) :
            raise ValueError("# activated pins mismatches request: ")

 
    def activatePinReading(self):
        """\
        
        Activate each of the pins mentioned in the input array for reading
        during the Arduino capture phase
        
        :param pinsToMeasure a list of pin names that are to be measured.
                    a name must be one of "LIGHT_0", "LIGHT_1", "AUDIO_0" or "AUDIO_1"
        :param pinMap dictionary that maps from pin name to pin number
        :param f: the file handle for serial communication with the Arduino
        :param wallClock: the wall clock providing times for the CSS_WC protocol 
         (wall clock protocol)
       
        """
        
        for pin in self.pinsToMeasure:
             arduino.samplePinDuringCapture(self.f, self.pinMap[pin], self.wallClock)
        

    def snapShot(self):
        """\
        
        take correlation between wall clock and sync time line
        
        :attribute syncTimelineClock the sync time line clock
        :attribute wallClock the wall clock
        :return the correlation, a tuple (wall clock value, corresponding sync time line value)
        
        """
        syncTimeNow = self.syncTimelineClock.ticks
        # convert from pts to wallclock
        wcNow = self.syncTimelineClock.toOtherClockTicks(self.wallClock, syncTimeNow)
        return (wcNow, syncTimeNow)


    def capture(self):
        """\
        
        initiate the data capture
        
        """
        if self.nActivePins > 0:
            correlationPre = self.snapShot()
            (self.channels, self.dueStartTimeUsecs, self.dueFinishTimeUsecs, timeDataPre, timeDataPost) = \
                                        captureAndPackageIntoChannels(self.f, self.pinsToMeasure, self.pinMap, self.wallClock)
            self.wcAcReqResp = {"pre":timeDataPre, "post":timeDataPost}
            correlationPost = self.snapShot()
            self.wcSyncTimeCorrelations = {"pre": correlationPre, "post": correlationPost}    
    
    
    def packageDispersionData(self, worstCaseDispersion):
        """\
        
        package up the dispersion data as needed for the detect module.
        This includes the worst case observed dispersion on the client entered by the operator
        
        :param correlationPre the correlation between the wall clock and the sync time line prior to sampling
        :param correlationPost the correlation between the wall clock and the sync time line after sampling
        :returns dictionary {"pre": (preWcTick, worstCaseDispersion), "post": (postWcTick, worstCaseDispersion)}
        
        """
        correlationPre = self.wcSyncTimeCorrelations["pre"]
        correlationPost = self.wcSyncTimeCorrelations["post"]
        preWcTick= correlationPre[0]
        postWcTick = correlationPost[0]
        self.wcDispersions = {"pre": (preWcTick, worstCaseDispersion), "post": (postWcTick, worstCaseDispersion)}


    def detectBeepsAndFlashes(self, wcPrecisionNanos, acPrecisionNanos):
        """\
        
        use the detect module to detect any flashes or beeps.
        
        :param syncClockTickRate the clock tick rate for the sync time line clock
        :param wcPrecisionNanos the wall clock precision in nanoseconds
        :param acPrecisionNanos the arduino clock's precision in nanoseconds
        
        """
        
        detector = detect.BeepFlashDetector(self.wcAcReqResp, self.syncClockTickRate, \
                                            self.wcSyncTimeCorrelations, self.wcDispersions, \
                                            wcPrecisionNanos, acPrecisionNanos)
        self.observedTimings = analyse.runDetection(detector, self.channels, self.dueStartTimeUsecs, self.dueFinishTimeUsecs)
        self.makeComparisonChannels()
 

 
    def makeComparisonChannels(self):
        """\
        
        prepare the measurement results, ready for iteration by the user of this service
        
        """
        self.testPackage = []
        for result in self.observedTimings:
            pinName = result["pinName"]
            self.testPackage.append( { "pinName":pinName,  "observed": result["observed"],  "expected":self.expectedTimings[pinName] } )



            
    def getComparisonChannels(self):
        """\
        
        :return the measurement results, ready for iteration by the user of this service
        
        """
        return self.testPackage   

     
       
       
    def doComparison(self, channel):
        """\
        
        run a comparison of observed and expected times for a given pin (represented by the channel input)
           
        :param channel a tuple
            { "pinName":pinName,  "observed": list of observed times,  "expected": list of expected times }
        :returns tuple summary of results of analysis.
            (index into expected times for video at which strongest correlation (lowest variance) is found, 
            list of expected times for video, 
            list of (diff, err) for the best match, corresponding to the individual time differences and each one's error bound) 
        :raise DubiousInput exception if the observed data is longer than the expected data
           
        Results are normalised to be in units of seconds since start of the test video sequence.
         
        """
        if  (len(channel["observed"]) - len(channel["expected"]) > 0) or len(channel["observed"]) == 0 :
            raise DubiousInput("poor data or no data")

        test = (channel["observed"], channel["expected"])
        matchIndex, expected, diffsAndErrors = analyse.doComparison(test, self.videoStartTicks, self.syncClockTickRate)
         
        # convert everything to units of seconds
        expectedSecs = [ ((e-self.videoStartTicks) / self.syncClockTickRate) for e in expected ] 
        diffsAndErrorsSecs = [ (d/self.syncClockTickRate, e/self.syncClockTickRate) for (d,e) in diffsAndErrors ]

        return matchIndex, expectedSecs, diffsAndErrorsSecs

def isAudio(pinName):
    """\
    
    Predicate to check whether the input corresponds to an audio- or light sensor-input

    :param pinName: indicates a pin to add to the set of pins to be read  during capture.
        one of "LIGHT_0", "AUDIO_0", "LIGHT_1", "AUDIO_1"
    :returns boolean: True if pin is associated with audio input on arduino
    and False otherwise (pin is connected to light sensor input
     
    """
    if pinName == "LIGHT_0" or pinName == "LIGHT_1":
        return False
    elif pinName == "AUDIO_0" or pinName == "AUDIO_1":
        return True
    else:
        raise ValueError("Unrecognised pin identifier: "+repr(pinName))



def repackageSamples(pinsToMeasure, pinMap, nMilliBlocks, samples):
    """\
    
    reformat the sample data into separate data channels that can be passed to
    the detect module
    
    :param pinsToMeasure: string array of pin names to be read  during capture.  An entry is one of:
        "LIGHT_0", "LIGHT_1", "AUDIO_0" and "AUDIO_1".
    :param pinMap dictionary to map from pin names to arduino pin numbers

    :param nMilliBlocks number of millisecond blocks in the sample data
    :param samples the arduino sample data.  Each millisecond block holds data
    for each activated pin, where that data are the high and low values observed
    on that pin over a millisecond
    :returns: the data channels for the sample data separated out per pin.  This is a
    list of dictionaries, one per sampled pin.
        A dictionary is { "pin": pin name, "isAudio": true or false, 
            "min": list of sampled minimum values for that pin (each value is the minimum over a millisecond period)
            "max": list of sampled maximum values for that pin (each value is the maximum over same millisecond period) }
    
    """
    
    possChannels = [None, None, None, None]
    for pinName in pinsToMeasure:
        possChannels[pinMap[pinName]] = ( { "pinName": pinName, "isAudio": isAudio(pinName), "min": [], "max": [] } )
    
    # put channels in same order as that returned by arduino        
    channels = []    
    for channel in possChannels:
        if channel != None:
            channels.append(channel)

    
    i = 0
    for blk in range(0, nMilliBlocks):
        for channel in channels:
            channel["max"].append(ord(samples[i]))
            i += 1
            channel["min"].append(ord(samples[i]))
            i += 1

    return channels






def captureAndPackageIntoChannels(f, pinsToMeasure, pinMap, wallClock):
    """\
    
    capture the data on the arduino, transfer it, and repackage 
    
    :param f: the file handle for serial communication with the Arduino
    :param pinsToMeasure: string array of pin names to be read during capture.  Names are
        LIGHT_0, LIGHT_1, AUDIO_0 and AUDIO_1.
    :param pinMap: dictionary that maps from pin name to arduino pin number
    :param wallClock: the wall clock providing times for the CSS_WC protocol (wall clock protocol)
    :returns a tuple: (data channels (see repackageSamples() )
        nanosecond time when sampling commenced,
        nanosecond time when sampling ended, 
        round trip timing data taken just before sampling started
        round trip timing data taken just after sampling finished )
    
    """
    
    dueStartTimeUsecs, dueFinishTimeUsecs, nMilliBlocks, timeDataPre, timeDataPost = arduino.capture(f, wallClock)
    samples = arduino.bulkTransfer(f, wallClock)[0]
    channels = repackageSamples(pinsToMeasure, pinMap, nMilliBlocks, samples)
    return (channels, dueStartTimeUsecs, dueFinishTimeUsecs, timeDataPre, timeDataPost)
