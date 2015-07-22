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

"""

Unit-tests for code that maps timings from arduino to synchronisation timeline
and also code that does the pulse detection.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/../src")


from detect import ConvertAtoB
from detect import ErrorBoundInterpolator
from detect import calcAcWcCorrelationAndDispersion
from detect import TimelineReconstructor
from detect import calcFlashThresholds
from detect import calcBeepThresholds
from detect import detectPulses
from detect import minMaxDataToEnvelopeData
from detect import timesForSamples
from detect import ArduinoToSyncTimelineTime
from detect import BeepFlashDetector


import unittest

class Test_ConvertAtoB(unittest.TestCase):
    def test_a2b(self):
        a2b = ConvertAtoB( (100,10), (200, 20) )
        self.assertEquals(a2b(150), 15.0)
        self.assertEquals(a2b(100), 10.0)
        self.assertEquals(a2b(200), 20.0)
        self.assertEquals(a2b(133), 13.3)
        
        

class Test_ErrorBoundInterpolator(unittest.TestCase):
    def testInterpolate(self):
        err = ErrorBoundInterpolator( (100, 0.5), (200, 0.7) )
        self.assertEquals(err(100), 0.5)
        self.assertEquals(err(150), 0.6)
        self.assertEquals(err(200), 0.7)
 
    def testOutOfBounds(self):
        err = ErrorBoundInterpolator( (100, 0.5), (200, 0.7) )
        self.assertRaises(ValueError, err, 99)
        self.assertRaises(ValueError, err, 201)

 
 
class Test_calcAcWcCorrelationAndDispersion(unittest.TestCase):
    def testSimple(self):
        
        wcT1 = 100
        acT2 = 1000
        acT3 = 1002
        wcT4 = 140
        
        wcPrecision=5
        acPrecision=2
        
        c,d = calcAcWcCorrelationAndDispersion( wcT1, acT2, acT3, wcT4, wcPrecision, acPrecision )

        self.assertEquals(c, (1001, 120))
        self.assertEquals(d, 38/2 + 5 + 2)



class Test_TimelineReconstructor(unittest.TestCase):
    def testSimple(self):
        history = [
            (100, (100, 1000, 1.0)),    # when time was 100, we observed that time 100 maps to timeline position 1000, and that the speed of timeline for 1
            (200, (100, 1000, 1.0)),    # when time was 200, we observed that the same relationship was true
            (300, (100, 1005, 1.0)),    # by time 300, we observed that the relationship had changed slightly
        ]
        parentTickRate = 100
        childTickRate = 1000
        interpolate = True
        
        reconstructor = TimelineReconstructor(history, parentTickRate, childTickRate, interpolate)

        # do tests, pretending we wind the clock back to when time was 120
        self.assertEquals(reconstructor(150, at=120), 1500)
        self.assertEquals(reconstructor(200, at=120), 2000)
        
        # now pretend we're after the 3rd observations - the relationship should have shifted
        self.assertEquals(reconstructor(110, at=300), 1105)
        
        # now pretend we're midway between 2nd and 3rd. Expect it to interpolate
        self.assertEquals(reconstructor(110, at=250), 1102.5)
        
        # cant reconstruct at a time before the first control timestamp was logged
        self.assertRaises(ValueError, reconstructor, 110, at=99)
        


class Test_calcThresholds(unittest.TestCase):

    def testFlashThresholds(self):
        hiSampleData = [ 1, 8, 8, 0, 0, 0, 3, 8, 8, 7, 4, 1, 0, 1, 0, 7, 9, 1, 7, 9, 8, 3, 0, 0, 0, 8, 9 ]
        loSampleData = [ 0, 7, 3, 0, 0, 0, 1, 6, 8, 7, 2, 0, 0, 0, 0, 5, 8, 0, 4, 9, 7, 1, 0, 0, 0, 1, 9 ]
        
        rising, falling = calcFlashThresholds(loSampleData, hiSampleData)
        
        self.assertEquals(rising, 6.0)
        self.assertEquals(falling, 3.0)

    def testBeepThresholds(self):
        sampleEnvelope = [12, 16, 16, 11, 1, 2, 2, 3, 1, 8, 12, 17, 5, 1, 1, 2, 6, 14, 9, 13, 14, 3, 2, 1, 2, 11, 12, 14, 17]

        rising, falling = calcBeepThresholds(sampleEnvelope)
        
        self.assertAlmostEqual(rising, 11.667, places=3)
        self.assertAlmostEqual(falling, 6.333, places=3)



class Test_detectPulses(unittest.TestCase):

    def testSimpleFlashScenario(self):

        risingThreshold = 7
        fallingThreshold = 4
        minPulseDuration = 0
        holdCount = 1

        #              IGNORE-              FIRST---                SECOND----------              IGNORE
        sampleData = [ 1, 8, 8, 0, 0, 0, 3, 8, 8, 7, 4, 1, 0, 1, 0, 7, 9, 1, 7, 9, 8, 3, 0, 0, 0, 8, 9 ]
        
        result = detectPulses(sampleData, risingThreshold, fallingThreshold, minPulseDuration, holdCount)
        self.assertEquals(result, [8.0, 17.5])


    def testSimpleBeepScenario(self):

        #                 IGNORE-------                      FIRST---------        
        hiSampleData = [  7,  9,  8,  2,  0,  1,  0,  2,  1,  0,  3,  8,  4, 1,  0,  1 ]
        loSampleData = [ -5, -7, -8, -9, -1, -1, -2, -1,  0, -8, -9, -9, -1, 0, -1, -1 ]
        
        #                     SECOND-----------                  IGNORE----
        hiSampleData.extend([ 2,  6,  0,  9,  8,  2, 2,  0,  1,  8,  6,  9,  9 ])
        loSampleData.extend([-4, -8, -9, -4, -6, -1, 0, -1, -1, -3, -6, -5, -8 ])
        
                         
        # offset it so it is not about 0
        loSampleData = map(lambda x:x+100, loSampleData)
        hiSampleData = map(lambda x:x+100, hiSampleData)

        envelope = minMaxDataToEnvelopeData(loSampleData, hiSampleData)
        
        self.assertEquals(envelope, [12, 16, 16, 11, 1, 2, 2, 3, 1, 8, 12, 17, 5, 1, 1, 2, 6, 14, 9, 13, 14, 3, 2, 1, 2, 11, 12, 14, 17])

        risingThreshold = 6
        fallingThreshold = 3
        minPulseDuration = 0
        holdCount = 0

        result = detectPulses(envelope, risingThreshold, fallingThreshold, minPulseDuration, holdCount)
        self.assertEquals(result, [10.5, 18.0])

        holdCount = 1
        result = detectPulses(envelope, risingThreshold, fallingThreshold, minPulseDuration, holdCount)
        self.assertEquals(result, [10.5, 18.0])

    def testNoisySamplesScenario(self):

        risingThreshold = 7
        fallingThreshold = 4
        minPulseDuration = 2
        holdCount = 1

        #              IGNORE-              FIRST---     |noise|     SECOND----------              IGNORE
        sampleData = [ 1, 8, 8, 0, 0, 0, 3, 8, 8, 7, 4, 1, 10, 1, 0, 7, 9, 1, 7, 9, 8, 3, 0, 0, 0, 8, 9 ]
        
        result = detectPulses(sampleData, risingThreshold, fallingThreshold, minPulseDuration, holdCount)
        self.assertEquals(result, [8.0, 17.5])



class Test_timesForSamples(unittest.TestCase):

    def test_timesForSamples(self):
        numSamples = 10
        acToStFunc= lambda x: (x*10 + 1000, 7)
        acFirstSampleStart=58
        acLastSampleEnd=78
        timesAndErrors=timesForSamples(numSamples, acToStFunc, acFirstSampleStart, acLastSampleEnd)

        self.assertEquals(timesAndErrors, [
            (1580, 7),
            (1600, 7),
            (1620, 7),
            (1640, 7),
            (1660, 7),
            (1680, 7),
            (1700, 7),
            (1720, 7),
            (1740, 7),
            (1760, 7),
            (1780, 7),
        ])



class Test_ArduinoToSyncTimelineTime(unittest.TestCase):
    """\
    scenario:
    
      sync.timeline         wall clock         arduino time
         (90kHz)              (nanos)             (nanos)
            |                    |                   |
    50,000  + - - -  200,000,000 + - - - 100,000,000 +  sync point between clocks/timelines
            |                    |                   |
            |                    |                   |
    50,090  + - - -  201,002,000 + - - - 101,000,000 +  start of first sample
            |                    |                   |
            |                    |                   |
           /\/                  /\/                 /\/
                   ... sampling happens during this period ...
           /\/                  /\/                 /\/
            |                    |                   |
            |                    |                   |
    50,990  + - - -  211,022,000 + - - - 111,000,000 +  end of last sample
            |                    |                   |
            |                    |                   |
    51,080  + - - -  212,024,000 + - - - 112,000,000 +  sync point between clocks/timelines
            
    error for arduino clock estimation is constant 144us
    error for wall clock estimation is constant 0.5ms
    """


    def test_simple(self):
    
        convAcWc  = lambda aNanos : (aNanos - 100000000) * 1.002 + 200000000
        calcAcErr = lambda aNanos : 144000   # 144 us
        convWcSt  = lambda wcNanos : (wcNanos - 200000000) * 90000 / 1002000000 + 50000
        wcDispCalc = lambda wcNanos : 0.5*1000000    # 0.5 ms
        stTickRate = 90000.0
        ac2st = ArduinoToSyncTimelineTime(convAcWc, calcAcErr, convWcSt, wcDispCalc, stTickRate)

        stTime, stErr = ac2st(111000000)
        self.assertEquals(stTime, 50990)
        self.assertEquals(stErr, 90000*(144/1000000.0 + 0.5/1000.0) + 1)

        stTime, stErr = ac2st(101000000)
        self.assertEquals(stTime, 50090)
        self.assertEquals(stErr, 90000*(144/1000000.0 + 0.5/1000.0) + 1)


    def testValuesUsedWithinRangeOnly(self):
        convAcWc  = lambda aNanos : (aNanos - 100000000) * 1.002 + 200000000
        
        def calcAcErr(aNanos):
            self.assertTrue(aNanos >= 100000000 and aNanos <= 112000000)
            return 144000        
        
        convWcSt  = lambda wcNanos : (wcNanos - 200000000) * 90000 / 1002000000 + 50000
        
        def wcDispCalc(wcNanos):
            self.assertTrue(wcNanos >= 200000000 and wcNanos <= 212024000)
            return  0.5*1000000        
        
        stTickRate = 90000.0
        ac2st = ArduinoToSyncTimelineTime(convAcWc, calcAcErr, convWcSt, wcDispCalc, stTickRate)

        stTime, stErr = ac2st(111000000)



class Test_BeepFlashTimingDetector(unittest.TestCase):
    """\
    scenario:
    
      sync.timeline         wall clock         arduino time
         (90kHz)              (nanos)             (nanos)
            |                    |                   |
    50,000  + - - -  200,000,000 + - - - 100,000,000 +  sync point between clocks/timelines (pre sampling)
            |                    |                   |
            |                    |                   |
    50,090  + - - -  201,002,000 + - - - 101,000,000 +  start of first sample
            |                    |                   |
            |                    |                   |
           /\/                  /\/                 /\/
     ... 10 x 1 millisecond samples taken during this period ...
           /\/                  /\/                 /\/
            |                    |                   |
            |                    |                   |
    50,990  + - - -  211,022,000 + - - - 111,000,000 +  end of last sample
            |                    |                   |
            |                    |                   |
    51,080  + - - -  212,024,000 + - - - 112,000,000 +  sync point between clocks/timelines (post sampling)
    
    
            
    We assume trip time each direction for arduino to PC clock sync is 144 us.
    We assume wall clock sync was measured with dispersions always of 0.5 ms.
    
    We assume wall clock precision of 1 us
    We assume arduino clock precision of 4 us
    """

    def test_beeps(self):
        US = 1000   # number of nanoseconds in one microsecond
    
        #                            ----pulse----
        loSamples = [ 130, 128, 116,  83,  76,  72, 124, 129, 125, 128 ]
        hiSamples = [ 130, 135, 146, 175, 176, 170, 134, 129, 130, 128 ]
        #            |                      |                         |
        # index      0                     4.5                        10
        # stTime   50090                  50495                      50990
        
        wcAcReqResp = {
            "pre" : (
                200000000 - 144*US, # t1 <wcNanos>,
                100000000,          # t2 <acNanos>,
                100000000,          # t3 <acNanos>,
                200000000 + 144*US, # t4 <wcNanos>,
            ),
            "post" : (
                212024000 - 144*US, # t1 <wcNanos>,
                112000000,          # t2 <acNanos>,
                112000000,          # t3 <acNanos>,
                212024000 + 144*US, # t4 <wcNanos>,
            ),
        }
        syncTimelineTickRate = 90000.0
        wcSyncTimeCorrelations = [
            (200000000, (200000000, 50000, 1.0)), # (<wcWhen>, (<wcNanos>, <syncTimelineTicks>, <speed>)),
            (212024000, (212024000, 51080, 1.0)), # (<wcWhen>, (<wcNanos>, <syncTimelineTicks>, <speed>)),
        ]
        wcDispersions = ErrorBoundInterpolator(
            (199000000, 0.5*1000000), # pre (<wcNanos>, <dispersionNanos>),
            (213024000, 0.5*1000000)  # post (<wcNanos>, <dispersionNanos>),
        )
        wcPrecisionNanos = 1 * US
        acPrecisionNanos = 4 * US
        
        detector = BeepFlashDetector(wcAcReqResp, syncTimelineTickRate, wcSyncTimeCorrelations, wcDispersions, wcPrecisionNanos, acPrecisionNanos)

        acStartNanos = 101000000
        acEndNanos   = 111000000
        beepDurationSeconds = 3 / 1000 # one sample = 1 millisecond
        beepTimings = detector.samplesToBeepTimings(loSamples, hiSamples, acStartNanos, acEndNanos, beepDurationSeconds)
        
        self.assertEquals(len(beepTimings), 1)
        ptsTime = beepTimings[0][0]
        error   = beepTimings[0][1]
        
        self.assertEquals(ptsTime, 50495)
        
        # check if error is equal to 1 pts tick + wcPrecision + acPrecision + acWcHalfRoundTrip + wcDispersion
        self.assertEquals(error, 1+(wcPrecisionNanos+acPrecisionNanos+144*US+0.5*1000000+0.5*1000000)*90000/1000000000)
        


if __name__ == "__main__":

    unittest.main()
