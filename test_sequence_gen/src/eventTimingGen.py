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

r"""\
Code for generating timings for sequences of events (such as flashes or beeps),
starting with generation 

Includes:

* a maximal-length-sequence bit stream generator to create unique patterns of bits

* a sequence encoder that transforms a bit stream into a set of timings of events
  where 0 and 1 are encoded with different patterns of events
  
* a means of transforming the times of events into start and end times for
  events if they all have a particular duration (e.g. the sample number at which
  a beep begins and ends, or the frame numbers containing the white pixels for
  a flash
  
* a means to generate a stream of values corresponding to audio samples or frames
"""


import itertools


def lfsr(bitLen, polycoeffs, iterationLimit=None):
    """\
    Linear feedback shift register generator.
    
    :param bitLen: The number of bits in the shift register.
    :param polycoeffs: The polynomial coefficients that determine where the feedback taps are.
    :param iterationLimit: The number of bit output before the generator finishes, or None for no limit.
    
    :returns: A generator function that yields the bit output from the shift register each cycle.
    
    Example:
    
    .. code-block:: python
    
        # generate a maximal length sequence for a 3 bit shift register
        polyCoeffs = [3,2]
        bits = 3
        
        mls = lfsr(bits, polyCoeffs, iterationLimit=7)
        for bit in mls:
            print bit
        1
        0
        1
        1
        1
        0
        0    
        
    """
    # initialise a non zero start state
    register = 1
    
    n=0
    while iterationLimit is None or n<iterationLimit:
        newBit=0
        for i in polycoeffs:
            newBit = newBit ^ register >> (bitLen-i)
        newBit = newBit & 1
        register = (register >> 1) | (newBit << (bitLen-1))
        yield newBit
        n=n+1
        

# taps came from http://en.wikipedia.org/wiki/Linear_feedback_shift_register
_mls_taps = {
     2: [2,1],
     3: [3,2],
     4: [4,3],
     5: [5,3],
     6: [6,5],
     7: [7,6],
     8: [8,6,5,4],
     9: [9,5],
    10: [10,7],
    11: [11,9],
    12: [12,11,10,4],
    13: [13,12,11,8],
    14: [14,13,12,2],
    15: [15,14],
    16: [16,14,13,11],
    17: [17,14],
    18: [18,11],
    19: [19,18,17,14],
}


"""\
With an MLS of N bits, you only need to observe N consecutive bits to uniquely
locate yourself anywhere in the (2**N)-1 length sequence
"""

def mls(bitLen, limitRepeats=1):
    """\
    Maximum length bit sequence generator.
    
    :param bitLen: The number of bits in the shift register.
    :limitRepeats: The number of repeats of the sequence to generate (default=1) or None to loop forever
    
    :returns: Generator function that yields a bit at a time for the sequence.
    """
    if limitRepeats is None:
        return lfsr(bitLen, _mls_taps[bitLen], iterationLimit=None)
    else:
        iterations = limitRepeats*(2**bitLen - 1)
        return lfsr(bitLen, _mls_taps[bitLen], iterationLimit=iterations)



def encodeBitStreamAsPulseTimings(bitStream, bitInterval, bitZeroTimings, bitOneTimings):
    """\
    :param bitStream: iterable or list of bit values (0s and 1s)
    :param bitInterval: the spacing to be used between each bit
    :param bitZeroTimings: a list of one or more timings for pulses used to represent a 0 bit
    :param bitOneTimings: a list of one or more timings for pulses used to represent a 1 bit
    :param startOffset: (default 0) an offset added to all outputted timings
    
    :return: A generator that yields a sequence of timings for pulses representing the encoded bit stream
    """
    n=0
    for bit in bitStream:
        if bit:  # bit == 1
            timings = bitOneTimings
        else:    # bit == 0
            timings = bitZeroTimings
        
        for timing in timings:
            t = n*bitInterval + timing
            yield t

        n=n+1



def genSequenceFromSampleIndices(toneStartEndTimings, gapGenFactory, eventGenFactory):
    """\
    :param toneStartEndTimings: An list or iterable (e.g. generator) that provides a sequence of tuples (start,end) indicating when tone is to occur.
    :param gapGenFactory: A function, that when called, returns a ready-to-go generator object that will yield sample values for gaps between events
    :param eventGenFactory: A function, that when called, returns a ready-to-go generator object that will yield sample values for events
    
    The tuples (start,end) are in ascending order of start times. The periods they
    represent must not overlap. 'start' is the index of the first sample of tone.
    and 'end' is the index of the first sample of gap after the event period.

    :returns: A generator that yields the individual samples making up the sequence    
    """
    n=0
    for (startIndex, endIndex) in toneStartEndTimings:
        gen = iter(gapGenFactory())
        while n < startIndex:
            yield gen.next()
            n=n+1
           
        gen = iter(eventGenFactory())
        while n < endIndex:
            yield gen.next()
            n=n+1
             

    # after last entry in event timings sequence, just output "gap"
    gen = gapGenFactory()
    while True:
        yield gen.next()
        

def genSequenceStartEnds(centreTimes, eventDuration, unitsPerSecond, sampleRate):
    """\
    Generator that takes a list or iterable describing the times of a sequence of events
    and yields the start and end times of those events
    
    :param centreTimes: A list or iterable for the times (in whatever units) since beginning of the sequence corresponding to the middle of each beep.
    :param eventDuration: The event duration (in units again)
    :param unitsPerSecond: The units of the list of times (e.g. 1.0 = seconds, 10.0 = 10ths of a second)
    :param sampleRate: The final sample rate we're aiming for.
    
    :returns: Iterable yielding pairs (start,end) corresponding to start and end sample indices.
    """
    halfEventDurationNumSamples = eventDuration / 2.0 / unitsPerSecond * sampleRate
    
    for centreTime in centreTimes:
        centreSampleNum = centreTime / unitsPerSecond * sampleRate
        
        startSampleNum = centreSampleNum - halfEventDurationNumSamples
        endSampleNum   = centreSampleNum + halfEventDurationNumSamples
        
        startSampleNum = int(round(startSampleNum))
        endSampleNum   = int(round(endSampleNum))
        
        yield (startSampleNum,endSampleNum)
        

def calcNearestDurationForExactNumberOfCycles(idealDurationSecs, cycleHz):
    """\
    Calculate and return the nearest duration (in seconds) to a specified ideal
    that is an exact whole number of cycles at a given frequency.
    
    :param idealDurationSecs: The idea duration (in seconds)
    :param cycleHz: Cycle frequency.
    
    :returns: The idea duration rounded to the nearest whole number of cycles at the specified frequency
    """
    cyclesInDuration = idealDurationSecs * cycleHz
    exactNumCycles = round(cyclesInDuration)
    return exactNumCycles / cycleHz



def secsToTicks(tSecs, startTick, tickRate):
    """\
    Convert seconds since a start tick value into the tick value it corresponds to.
    
    :param tSecs: Seconds since some arbitrary reference point (e.g. the start of the video)
    :param startTick: The tick value at the same arbitrary reference point (e.g. the start of the video)
    :param tickRate: The tick rate (in Hz)
    
    :returns: the time value converted to the equivalent tick value
    """
    return tSecs * tickRate + startTick


