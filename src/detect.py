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


"""\
This module provides data processing functions to enable measurement of the
accuracy with which the light and sound emitted by a TV Device or Companion Screen Application
corresponds to the timeline timing information communicated via the DVB protocols.

It is assumed that the device being measured plays a specifically crafted test
audio/video clip containing easy to detect "events" in the form of regular flashes
or beeps (consisting of a single frame flash of white over a black background, or
a single frame duration burst of a tone that punctuates silence).

The system performing the measurement consists of two parts:

1. A device pretending to be either the TV Device (when measuring a companion)
   or the companion (when measuring a TV Device)

2. A device capturing light and audio samples

It is assumed that the capture device is separate and has its own separate clocks
against which the data it captures is timed.

The functions here can be used to take the following data as input:

* raw sample data recorded by capture hardware
* the relationship between time on the capturing hardware and the "wall clock" and
* some of the timing information sent or received via the DVB protocols.

... and from this data calculate the times at which the flashes and beeps occurred
in terms of the synchronisation timeline and quantify the error bounds of each
measurement taking all possible sources of error into account.

These timings can then be compared against when the beeps and flashes were expected to occur
on the timeline of the media.


What data is needed
-------------------

We need the following information to detect the flashes or beeps in sample data
and to calculate how this related to the synchronisation timeline.


**1. Clock sync measurments between Arduino clock and PC Wall Clock**

The Wall Clock on the PC needs to be synchronised with the internal clock
of the Arduino. We do a simple request-response clock measurement (like the
CSS-WC protocol but even more simplified) before ("pre") and after ("post")
the arduino performed its sampling process. The times are all in nanoseconds:
    
.. code-block:: python
    
    wcAcReqResp = {
        "pre" : (                  # request-response from before sampling
            1424652124816656128,   # t1 : PC Wall Clock time request was sent (ns).
            58200015000,           # t2 : Arduino time at which request was received (ns).
            58200015000,           # t3 : Arduino time at which response was sent (ns).
            1424652124817006128,   # t4 : PC Wall Clock time response was received (ns).
        },
        "post" : (                 # request-response from after sampling
            1424652140817006128,   # t1 : PC Wall Clock time request was sent (ns).
            74200018000,           # t2 : Arduino time at which request was received (ns).
            74200018000,           # t3 : Arduino time at which response was sent (ns).
            1424652140817346128,   # t4 : PC Wall Clock time response was received (ns).
        },
    }    


**2. The tick rate of the synchronisation timeline (in Hz).**

For example, 90kHz for a PTS timeline:

.. code-block:: python

    syncTimelineTickRate = 90000     # timeline tick rate in Hz


**3. Correlations that map from Wall Clock to Synchronisation Timeline**

Two correlations are needed: one for just before sampling began (pre) and one
for just after sampling finished (post). These are just like Control Timestamps,
but the Wall Clock time must correspond to a time just before sampling began
and just after it ended.

To generate these two values, you should use your understanding of how Wall Clock
and synchronisation timeline correlate before and after sampling to calculate
a suitable pair of values for each.

.. code-block:: python

    wcSyncTimeCorrelations= {
        "pre" :  (1424652124809156128, 18320500),
        "post" : (1424652140823546128, 19761795),
    }


**4. The dispersion of the wall clock.**

The argument can either be a function that, for any given wall clock time 
returns the dispersion in nanoseconds; or it can be a pair of wall clock time
and dispersion values. Examples of both are shown below.

If the measurements were taken (by pretending to be a Companion App) of a device
in the TV Device role (e.g. HbbTV master terminal) then the dispersion is that
of the PC that connected as a client to perform these measurments. For example:

.. code-block:: python

    wcDispersions = {
        "pre"  : ( 1424652124809156128, 1400000.0 ),  # 1.4ms dispersion at a time just before sampling
        "post" : ( 1424652140823546128, 1500000.0 ),  # 1.5ms dispersion at a time just after sampling
    }

If the measurmenets were taken (by pretending to be the TV Device) of a device
in the Companion Screen App role (or an HbbTV slave terminal) then the
dispersion is that of the Companion or slave.

For example, an HbbTV slave terminal generates dispersion values while it is 
synchronising to the measurement system (in the role of the master) might report
a dispersion values of which the greatest is recorded by the application on the
slave terminal:

.. code-block:: python

    def wcDispersions(wcTimeNanos):
        return 2.4*1000000              # 2.4ms dispersion at any wall clock time


**5. Wall Clock and Arduino clock measurement precision**

Finally, to complete calculation of error bounds, we also need to know the
precision with which the PC measured the Wall Clock and the Arduino can measure
its clock. Both, again, are expressed in nanoseconds. For example:

.. code-block:: python

    wcPrecisionNanos = 170000      # PC measures Wall Clock to within 170 microseconds
    acPrecisionNanos = 4000        # Arduino clock meausred to within 4 microseconds

Finally we provide the sample data as lists of sample values. One list contains
the minimum values seen during each sample period. the other contains the
maximum values seen during each sample period. For example:

.. code-block:: python

    loSamples = [ 130, 128, 116,  83,  76,  72, 124, 129, 125, 128, ... ]
    hiSamples = [ 130, 135, 146, 175, 176, 170, 134, 129, 130, 128, ... ]


Performing the beep/flash detection and calculations
----------------------------------------------------

Once we have all the data needed, as described above, then we can use the code
in this module to perform the calculation:

.. code-block:: python

    import detect

    detector = detect.BeepFlashDetector(wcAcReqResp, syncTimelineTickRate, wcSyncTimeCorrelations, wcDispersions, wcPrecisionNanos, acPrecisionNanos)
    
    if IS_AUDIO_DATA:
        func = detector.samplesToBeepTimings
    else:
        func = detector.samplesToFlashTimings

    timings = func(loSampleData, hiSampleData, acStartNanos, acEndNanos)
      
    for (eventTime, errorBound) in timings:
        print "Detected flash/beep at timeline tick value %f with error margin +/- %f ticks" % (eventTime, errorBound)

      
`timings` contains a list of tuples. Each tuple represents a detected
flash or beep. The tuple contains (time, errorBound) representing the time of the
middle of the flash or beep, with an uncertainty of +/- errorBound.

Both the time and errorBound are in units of ticks of the synchronisation timeline.
        
The final output might, for example, be:

    [ ( 1520, 15), (1702, 8), (1996, 25) ]
    
Meaning that 3 flashes/beeps were detected, and giving the (time, errorbound) for
each in units of ticks of the synchronisation timeline.



"""

# ---------------------------------------------------------------------------


class ConvertAtoB(object):
    def __init__(self, (a1, b1), (a2, b2)):
        """\
        Returns a function that maps from reference frame A to reference frame B
        where the relationship is defined by a straight line passing through
        the points (a1,b1) and (a2,b2) if you think of A as being the X axis and
        B as being the Y axis.
        
        For example, the halfway point between a1 and a2 will map to the halfway
        point between b1 and b2.
        
        It will also extrapolate the line beyond the points provided.
        
        Example mapping values between 0 and 10 to values between 50 and 70:
        
        .. code-block:: python
        
            >>> a1b1 = (0,50)
            >>> a2b2 = (10,70)
            >>> convert = ConvertAtoB( a1b1, a2b2 )
            >>> print convert(0)
            50.0
            >>> print convert(5)
            60.0
            >>> print convert(10)
            70.0
            >>> print convert(15)
            80.0
        
        
        :param a1: Value for first correlation from reference frame A
        :param b1: Value for first correlation from reference frame B
        :param a2: Value for second correlation from reference frame A
        :param b2: Value for second correlation from reference frame B
        
        :returns: A function that takes a value in reference frame A as an argument and returns the corresponding value in reference frame B.
        """
        super(ConvertAtoB, self).__init__()
        self.a1, self.b1 = (a1, b1)
        self.a2, self.b2 = (a2, b2)
    
    def __call__(self, a):
        return (float(a) - self.a1) * (self.b2-self.b1) / (self.a2-self.a1) + self.b1
    


class ErrorBoundInterpolator(object):
    def __init__(self, (v1, e1), (v2, e2)):
        """\
        Given to different points at which readings were taken and the error bounds
        of those readings at those points, then interpolates the error during the
        period between those points.
        
        
        Will not work outside the bounds    
        """
        super(ErrorBoundInterpolator,self).__init__()
        if v1 >= v2:
            raise ValueError("v1 must be less than v2.")
        self.lo = v1
        self.hi = v2
        self._a2b = ConvertAtoB( (v1, abs(e1)), (v2, abs(e2)) )
        
    def __call__(self, v):
        if v<self.lo or v>self.hi:
            raise ValueError("Cannot extrapolate error for "+str(v)+" because it is outside of the range from "+str(self.lo)+" to "+str(self.hi)+" covered by the interpolator.")
        return self._a2b(v)


def calcAcWcCorrelationAndDispersion( wcT1, acT2, acT3, wcT4, wcPrecision, acPrecision ):
    """\
    Returns correlation and dispersion at the time of the correlation given
    t1, t2, t3, t4 from a clock sync request-response exchange and knowledge of
    the precision of both clocks.
    
    :param wcT1: t1 measurement (of Wall clock) in nanoseconds
    :param acT2: t2 measurement (of Arduino clock) in nanoseconds
    :param acT3: t3 measurement (of Arduino clock) in nanoseconds
    :param wcT4: t4 measurement (of Wall clock) in nanoseconds
    :param wcPrecision: measurement precision of Wall Clock in nanoseconds
    :param acPrecision: measurement precision of Arduino Clock in nanoseconds
    
    :returns: ( (acTimeNanos, wcTimeNanos), dispersionNanos )
    """
    correlation = ( (acT2 + acT3) / 2.0, (wcT1 + wcT4) / 2)
    rtt = (wcT4 - wcT1) - ( acT3 - acT2 )
    dispersion = rtt / 2.0 + wcPrecision + acPrecision
    return correlation, dispersion



class TimelineReconstructor(object):

    def __init__(self, timestampedControlTimestamps, parentTickRate, childTickRate, interpolate):
        """\
        Takes a history of control timestamp style data (correlations and
        a speed multiplier value) that were recorded at particular times on
        the parent timeline, and uses them to convert parent to child timeline
        values while pretending to be at any point in that history.
        
        E.g. can be a history of control timestamps relating wall clock time
        to sync. timeline time that was received via CSS-TS and be used to
        convert wall clock times to sync timeline times using only the
        information available at any particular point in the past.
        
        :param timestampedControlTimestamps: list of tuples: (parentTimeAt, (parentTime,timelineTime, speed))
        :param parentTickRate: tick rate of parent timeline (ticks per second)
        :param timelineTickRate: tick rate of timeline being reconstructed
        :param interpolate: if True, then (assuming speeds don't change) will interpolate between consecutive control timestamps
        """
        self.controlTimestamps = sorted(timestampedControlTimestamps)
        self.parentTickRate = float(parentTickRate)
        self.childTickRate = float(childTickRate)
        self.interpolate = interpolate
        
    def __call__(self, parentTime, at=None):
        """\
        :param v: Time on the parent timeline to be converted
        :param at: Time on the parent timeline at which to make the conversion
        :returns: Corresponding time on the reconstructed timeline
        """
        
        if at == None:
            at = parentTime
        
        # first find the control timestamp "most recent" and the one after
        # (if there is one)
        controlTimestamp = None
        nextControlTimestamp = None
        for when, cT in self.controlTimestamps:
            if when <= at:
                controlTimestamp = when, cT
            else:
                nextControlTimestamp = when, cT
                break
            
        if controlTimestamp is None:
            raise ValueError("Asked for a conversion at a time at which no control timestamps had yet arrived.")

        tWhen, (tParent, tChild, tSpeed) = controlTimestamp
        
        if nextControlTimestamp is not None:
            nWhen, (nParent, nChild, nSpeed) = nextControlTimestamp
        else:
            nWhen, (nParent, nChild, nSpeed) = None, (None,None,None)
        
        # if there is a next control timestamp and speed matches, then try to interpolate
        if self.interpolate and nextControlTimestamp is not None and tSpeed == nSpeed:

            # calc what time would be using the most recent (tXXX) and next (nXXX)
            # control timestamps
            t = (parentTime - tParent) * tSpeed / self.parentTickRate * self.childTickRate + tChild
            n = (parentTime - nParent) * nSpeed / self.parentTickRate * self.childTickRate + nChild

            # now interpolate
            interpolator=ConvertAtoB((tWhen,t), (nWhen,n))
            return interpolator(at)
            
        else:
            # else perform by extrapolation, ignoring the next control timestamp 
            return (parentTime - tParent) * tSpeed / self.parentTickRate * self.childTickRate + tChild
        

# ---------------------------------------------------------------------------

class ArduinoToSyncTimelineTime(object):
    def __init__(self, convAcWc, calcAcErr, convWcSt, wcDispCalc, stTickRate):
        """\
        Class that can convert an arduino time (in nanos) to a synchronisation
        timeline time, plus error bound (both in units of sync timeline ticks)
        
        :param convAcWc:   function that converts from arduino time (nanos) to wall clock time (nanos)
        :param calcAcErr:  function that returns the error bound (nanos) for a given arduino time value (nanos)
        :param convWcSt:   function that returns a sync timeline tick value for a given wall clock time value (nanos)
        :param wcDispCalc: function that returns dispersion (nanos) of wall clock for a given wall clock time (nanos)
        :param stTickRate: Tick rate of synchronisation timeline (ticks per second)
        """
        super(ArduinoToSyncTimelineTime, self).__init__()
        self.convAcWc = convAcWc
        self.calcAcErr = calcAcErr
        self.convWcSt = convWcSt
        self.wcDispCalc = wcDispCalc
        self.stTickRate = stTickRate
        
    def __call__(self, aNanos):
        """\
        For a given arduino clock time (in nanos) convert it to a sync timeline
        time and error bound (both expressed in fractional ticks of the sync timeline)
        
        :param aTime: arduino time (in nanos)
        :returns: tuple (<syncTimelineTicks>, <errorBoundTicks>)
        """
        wcNanos = self.convAcWc(aNanos)
        stTicks = self.convWcSt(wcNanos)

        errorNanos = self.calcAcErr(aNanos) + self.wcDispCalc(wcNanos)
        errorTicks = errorNanos * self.stTickRate / 1000000000.0
        errorTicks = errorTicks + 1.0 # could be out by up to +/- 1 sync timeline tick (precision limit)

        return (stTicks, errorTicks)



def timesForSamples(numSamples, acToStFunc, acFirstSampleStart, acLastSampleEnd):
    """\
    Calculates the sync timeline times corresponding 
    
    :param numSamples: number of samples over the period
    :param acToStFunc: function that converts arduino time (nanos) to sync timeline ticks and error bound tick tuples
    :param acFirstSampleStart: arduino time (nanos) of the beginning of the first sample period 
    :param acLastSampleEnd: arduino time (nanos) of the end of the last sample period 

    :returns: list of tuples of sync timeline time (ticks) and error bound (ticks) corresponding to start of each sample (or end of previous)
    """
    stTimesErrs = []
    for i in range(0,numSamples+1):
        acTime = acFirstSampleStart + float(acLastSampleEnd - acFirstSampleStart) * i / numSamples
        (tTicks, errTicks) = acToStFunc(acTime)
        stTimesErrs.append( (tTicks, errTicks) )
        
    return stTimesErrs




def calcFlashThresholds(loSampleData, hiSampleData):
    """\
    Analyses light sensor sample data and returns suggestions for the thresholds needed to detect the flashes.
    
    :param loSampleData: list of sample values, where each value is the lowest seen during that sampling period
    :param loSampleData: list of sample values, where each value is the highest seen during that sampling period
    :returns: tuple (rising, falling) consisting of suggested rising-edge and falling-edge detection thresholds for use in the pulse detection code.
    """
    lo = min(loSampleData)
    hi = max(hiSampleData)
    risingThreshold  = (lo + 2*hi) / 3.0
    fallingThreshold = (lo*2 + hi) / 3.0
    return risingThreshold, fallingThreshold
    
def calcBeepThresholds(envelopeSampleData):
    """\
    Analyses audio sample data and returns suggestions for the thresholds needed to detect the beeps.
    
    :param loSampleData: list of sample values, where each value is the lowest seen during that sampling period
    :param loSampleData: list of sample values, where each value is the highest seen during that sampling period
    :returns: tuple (rising, falling) consisting of suggested rising-edge and falling-edge detection thresholds for use in the pulse detection code.
    """
    lo = min(envelopeSampleData)
    hi = max(envelopeSampleData)
    risingThreshold  = (lo + 2*hi) / 3.0
    fallingThreshold = (lo*2 + hi) / 3.0
    return risingThreshold, fallingThreshold

def detectPulses(hiSampleData, risingThreshold, fallingThreshold, minPulseDuration, holdCount):
    """\
    Pulse detection state machine. Returns a list of indices into the sample
    data provided for the centre points of the detected pulses.
    
    :param sampleData: list of sample values
    :param risingThreshold: threshold for low to high transition
    :param fallingTreshold: threshold for high to low transition
    :param minPulseDuration: the minimum number of samples a pulse must last for for it to be considered
    :param holdCount: number of samples to hold a high state for
    
    If first data above the rising threshold occurs at index i where
    i <= holdCount then it will not be reported as a pulse until the state machine
    has transitioned back to the low state.
    
    :returns: list of indices of the centre times of each pulse that is detected. Values are all floating point and may include 'halfway' indices, e.g. 14.5
    """
    pulseIntervals = []
    
    LO = 0
    HI = 1
    
    state = HI
    ignoreFirstPulse = True
    latestHi = -1

    for i in range(0, len(hiSampleData)):
        v = hiSampleData[i]
        if state == LO:
            if v >= risingThreshold:
                state = HI
                hiTransitionIndex = i
                latestHi = i
                
        elif state == HI:
            if v > fallingThreshold:
                latestHi = i
            else:
                if v <= fallingThreshold:
                    if i - latestHi > holdCount:
                        state = LO
                        if not ignoreFirstPulse:
                            pulseStart    = hiTransitionIndex
                            pulseEnd      = latestHi+1
                            pulseDuration = pulseEnd - pulseStart
                            if pulseDuration >= minPulseDuration:
                                pulseIntervals.append((pulseStart, pulseEnd))
                        ignoreFirstPulse=False
                        
        else:
            raise RuntimeError("Unexpected state reached in pulse detector.")

    # list currently contains intervals, convert to indices of the centre point (which might be at a halfway)
    # the end values are the positions where it went back to low, therefore the last high is end-1
    pulseIndices = map(lambda (start,end) : (start+(end-1))/2.0, pulseIntervals)
    return pulseIndices


def minMaxDataToEnvelopeData(loSampleData, hiSampleData):
    """\
    Takes sample data representing the lo and high values seen during each sample
    period, and fuses them into a single value representing the difference between
    min and max (i.e. the size of the envelope for that sample)
    
    :param loSampleData: list of sample values, where each value is the lowest seen during that sampling period
    :param loSampleData: list of sample values, where each value is the highest seen during that sampling period
    """
    return map(lambda lo, hi: hi-lo, loSampleData, hiSampleData)


def detectFlashes(loSampleData, hiSampleData, minFlashDuration, holdCount):
    """\
    Takes light sensor sample data and returns the indices of the centre times of
    light flashes. Calibrates the detection process against the data itself.
    
    :param loSampleData: list of sample values, where each value is the lowest seen during that sampling period
    :param loSampleData: list of sample values, where each value is the highest seen during that sampling period
    :param minFlashDuration: the minimum number of samples a flash must last for
    :param holdCount: the high-value hold duration (in units of a whole number of sampling periods)
    :returns: list of sample indices corresponding to the centre of each detected flash. Values are floating point and may be midway between indices.
    """
    risingThreshold, fallingThreshold = calcFlashThresholds(loSampleData, hiSampleData)
    return detectPulses(hiSampleData, risingThreshold, fallingThreshold, minFlashDuration, holdCount)


def detectBeeps(loSampleData, hiSampleData, minBeepDuration, holdCount):
    """\
    Takes audio sample data and returns the indices of the centre times of
    beeps. Calibrates the detection process against the data itself.
    
    :param loSampleData: list of sample values, where each value is the lowest seen during that sampling period
    :param loSampleData: list of sample values, where each value is the highest seen during that sampling period
    :param minBeepDuration: the minimum number of samples a beep must last for
    :param holdCount: the high-value hold duration (in units of a whole number of sampling periods)
    :returns: list of sample indices corresponding to the centre of each detected beep. Values are floating point and may be midway between indices.
    """
    envelopeSampleData = minMaxDataToEnvelopeData(loSampleData, hiSampleData)
    risingThreshold, fallingThreshold = calcBeepThresholds(envelopeSampleData)
    return detectPulses(envelopeSampleData, risingThreshold, fallingThreshold, minBeepDuration, holdCount)


# ---------------------------------------------------------------------------

import math


class BeepFlashDetector(object):
    """\
    Class that provides functions to take arduino sampling measurements and other
    data and translate this to times (on the synchronisation timeline) corresponding
    to the flashes or beeps in the sampling data. The output includes calculated
    error bounds.
    
    """

    def __init__(self, wcAcReqResp, syncTimelineTickRate, wcSyncTimeCorrelations, wcDispersions, wcPrecisionNanos, acPrecisionNanos, interpolateWc2St=True):
        """
        :param wcAcReqResp: Dict containing "pre" and "post" sampling period clock sync request and response timings
        between the Wall Clock and Arduino clock (both in nanos).
        Structure should be a dict with "pre" and "post" keys. For both, the value is a 4-tuple (t1, t2, t3, t4) 
        where, for both, t1, t2, t3, t4 represent:
        * PC time at which request was sent by the PC (t1),
        * Arduino time at which request was received by the Arduino (t2),
        * Arduino time at which response was sent by the Arduino (t3)
        * PC time at which response was received by the PC (t4)
        
        :param syncTimelineTickRate: The tick rate (in Hz) of the synchronisation timeline used for the CSS-TS exchanges

        :param wcSyncTimeCorrelations: A list of tuples of the form (wcTimeAt,(wcTime, stTime, speed)) 
        where wcTime,stTime is the correlation between wall clock time and synchronisation
        timeline time and speed is the timelinespeed multiplier at that point and
        wcTimeAt is the wall clock time at which this correlation applied (e.g.
        the time at which it was received from a CSS-TS server).
        The list must contain at least one item, and that must have wcTimeAt
        corresponding to some point shortly before measurement sampling began.
        
        :param wcDispersions: A function that returns the dispersion (in nanoseconds)
        of the Wall clock at a given wall clock time during the measurement period.
                
        :param wcPrecisionNanos: The precision with which the wall clock was measured (in nanoseconds) when synchronising it with the Arduino clock.

        :param acPrecisionNanos: The precision with which the Arduino clock was measured by the Arduino (in nanoseconds) when synchronising it with the Wall Clock
        
        :param interpolateWc2St: (Default True). If True, then conversions between wallclock and sync timeline times will, where possible, be done via interpolation. 
        """
        
        super(BeepFlashDetector, self).__init__()
        
        # generate correlations and error bounds for the two points at which
        # the wall clock and arduino clock are synchronised ("pre" and "post"
        # the sampling process)
        acWcCorr = {}
        acWcDisp = {}

        t1, t2, t3, t4 = wcAcReqResp["pre"]
        acWcCorr["pre"], acWcDisp["pre"] = calcAcWcCorrelationAndDispersion(t1, t2, t3, t4, wcPrecisionNanos, acPrecisionNanos)
    
        t1, t2, t3, t4 = wcAcReqResp["post"]
        acWcCorr["post"], acWcDisp["post"] = calcAcWcCorrelationAndDispersion(t1, t2, t3, t4, wcPrecisionNanos, acPrecisionNanos)
    
        # create an object that can convert between arduino and wall clock time
        ac2wc = ConvertAtoB(acWcCorr["pre"], acWcCorr["post"])
        
        # create an object that can calculate error bound on arduino time estimates
        # given a particular arduino time (ignoring sampling resolution atm)
        acPreTime = acWcCorr["pre"][0]
        acPostTime = acWcCorr["post"][0]

        ac2acErr = ErrorBoundInterpolator( (acPreTime, acWcDisp["pre"]), (acPostTime, acWcDisp["post"]) )
        
        wc2wcDisp = wcDispersions
        
        # create object to convert wall clock time to sync timeline time
        #wc2st = ConvertAtoB(wcSyncTimeCorrelations["pre"], wcSyncTimeCorrelations["post"])
        wc2st = TimelineReconstructor(wcSyncTimeCorrelations, 1000000000, syncTimelineTickRate, interpolateWc2St)
        
        # create object that can convert from arduino time to sync timeline time
        self.ac2st = ArduinoToSyncTimelineTime(ac2wc, ac2acErr, wc2st, wc2wcDisp, syncTimelineTickRate)
    


    def samplesToFlashTimings(self, loSampleData, hiSampleData, acStartNanos, acEndNanos, flashDurationSecs):
        """\
        Takes sample data recorded by the arduino light sensor and detects flashes from it,
        translating that to times on the synchronisation timeline (including error bounds)
        so that it can be compared to the expected timings of the flashes.
        
        :param loSampleData: list of sample values corresponding to the minimum values seen during each sample period.
        :param hiSampleData: lost of sample values corresponding to the maximum values seen during each sample period.
        :param acStartNanos: the Arduino clock time at which the first sampling period began (in nanoseconds)
        :param acEndNanos: the Arduino clock time at which the last sampling period ended (in nanoseconds)
        :param flashDurationSecs: the approximate duration (in seconds) of a flash

        :returns: a list of tuples. Each tuple represents a detected flash.
        The tuple contains (time, errorBound) representing the time of the
        middle of the flash, with an uncertainty of +/- errorBound. 
        
        """
        # calculate a hold time for the flash detection process based on the hint about flash duration
        # set it quite long to cope with backlight flicker issues
        holdTime = flashDurationSecs * 0.5    # half of the flash duration
        holdCount = int(holdTime * 1000)     # one sample = 1 millisecond
	minFlashDuration = flashDurationSecs * 0.5
        minFlashCount = int(minFlashDuration * 1000)
        
        # run the detection
        detectFunc = detectFlashes
        return self.convertSamplesToDetectionTimings(loSampleData, hiSampleData, acStartNanos, acEndNanos, detectFunc, minFlashCount, holdCount)

        
    def samplesToBeepTimings(self, loSampleData, hiSampleData, acStartNanos, acEndNanos, beepDurationSecs):
        """\
        Takes sample data recorded by the arduino audio input and detects beeps from it,
        translating that to times on the synchronisation timeline (including error bounds)
        so that it can be compared to the expected timings of the beeps.
        
        :param loSampleData: list of sample values corresponding to the minimum values seen during each sample period.
        :param hiSampleData: lost of sample values corresponding to the maximum values seen during each sample period.
        :param acStartNanos: the Arduino clock time at which the first sampling period began (in nanoseconds)
        :param acEndNanos: the Arduino clock time at which the last sampling period ended (in nanoseconds)
        :param beepDurationSecs: the approximate duration (in seconds) of a beep

        :returns: a list of tuples. Each tuple represents a detected beep.
        The tuple contains (time, errorBound) representing the time of the
        middle of the beep, with an uncertainty of +/- errorBound. 
        
        """
        # calculate a hold time for the flash detection process based on the hint about beep duration
        # set it quite long to cope with badly shaped waveforms
        holdTime = beepDurationSecs * 0.5    # half of the beep duration
        holdCount = int(holdTime * 1000)     # one sample = 1 millisecond
	minBeepDuration = beepDurationSecs * 0.75
        minBeepCount = int(minBeepDuration * 1000)
        
        # run the detection
        detectFunc = detectBeeps
        return self.convertSamplesToDetectionTimings(loSampleData, hiSampleData, acStartNanos, acEndNanos, detectFunc, minBeepCount, holdCount)

        
    def convertSamplesToDetectionTimings(self, loSampleData, hiSampleData, acStartNanos, acEndNanos, detectFunc, minPulseDuration, holdCount):
        
        # determine indexes in the sample data corresponding to centre time of each pulse
        pulseIndices = detectFunc(loSampleData, hiSampleData, minPulseDuration, holdCount)
        
        # generate list of timings corresponding to start time of each sample
        stTimesAndErrors = timesForSamples(
            numSamples=len(loSampleData),
            acToStFunc=self.ac2st,
            acFirstSampleStart=acStartNanos,
            acLastSampleEnd=acEndNanos
        )
        
        timings = []
        
        for index in pulseIndices:
        
            # detect pulse function assumed indices correspond to the centre of each
            # we are about to use to calculate using times where the index corresponds
            # to the beginning of the sample, so adjust
            index=index+0.5

            # index is fractional, so we interpolate between the times and errors
            # of the neighbouring sample boundaries
            floorIndex = int(math.floor(index))
            fracIndex = index-floorIndex
            nextIndex = floorIndex + 1
            
            time1, err1 = stTimesAndErrors[floorIndex]
            time2, err2 = stTimesAndErrors[nextIndex]
            
            time = fracIndex * time2 + (1.0-fracIndex) * time1
            err  = fracIndex * err2  + (1.0-fracIndex) * err1
            
            errDueToSampleDuration = (time2 - time1 ) / 2.0
            
            totalErr = err + errDueToSampleDuration
            
            pulseTimeAndError = (time,totalErr)
            
            timings.append(pulseTimeAndError)
            
        return timings
        
    
    
if __name__ == '__main__':
    # unit tests in:
    #    ../tests/test_detect.py
    pass
    
