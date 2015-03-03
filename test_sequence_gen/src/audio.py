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
Code to generate WAV files containing silence interspersed by beeps (bursts of tone)
based from a list of times of when the beeps are to occur.

Example usage:

.. code-block:: python

    # create 2 seconds of audio with 0.1 second duration beeps centred at 0.5, 1 and 1.5 seconds after
    # the start of the audio
    
    beepTimesSecs = [ 0.5, 1, 1.5 ]
    beepDurationSecs = 0.1
    seqDurationSecs = 2
    sampleRateHz = 48000
    toneHz = 3000
    amplitude = 32767*0.5  # half full amplitude (samples are 16 bit signed)
    
    seq = genBeepSequence(beepTimesSecs, beepDurationSecs, seqDurationSecs, sampleRateHz, toneHz, amplitude)
    
    savAsWavFile(seq, "audio.wav", sampleRateHz)
    
"""

import itertools
import math
import struct
import wave

from eventTimingGen import calcNearestDurationForExactNumberOfCycles
from eventTimingGen import genSequenceStartEnds
from eventTimingGen import secsToTicks
from eventTimingGen import genSequenceFromSampleIndices


def saveAsWavFile(seq, filename, sampleRateHz):
    """\
    Saves sample data in a list (or iterable object) to a file as a mono WAV file.
    
    :param seq: list or iterable containing numbers corresponding to 16 bit signed sample values
    :param filename: The filename to write to
    :param sampleRateHz: The sample rate of the sample data
    """
    # turn into signed 16 bit little-endian raw samples
    values = list(seq)
    num = len(values)
    sampleData = struct.pack("<"+str(num)+"h", *values)
    
    # write data out as a WAV file
    wav = wave.open(filename, "wb")
    
    wav.setnchannels(1)            # mono
    wav.setsampwidth(2)            # 16 bit (2 byte) samples
    wav.setframerate(sampleRateHz) 
    wav.setcomptype("NONE","NONE")
    wav.writeframes(sampleData)
    wav.close()


def GenTone(sampleRateHz, peakValue, toneHz, phaseOffsetCycles=0.0):
    """\
    Generator that yields audio sample values for a tone at the specified amplitude and frequency for a given sample rate.
    
    :param sampleRateHz: The sample rate for the samples to be outputted
    :param peakValue: The peak amplitude of the tone to be generated
    :param toneHz: The frequency of the tone to be generated
    :param phaseOffsetCycles: The phase at which the sine wave starts (default=0.0). 0.5 = half cycle out of phase.
    
    :returns: Generator that yields sample values
    """
    
    samplesPerCycle = sampleRateHz / float(toneHz)
    n=0
    while True:
        # doing the calculation this way to avoid cumulative errors (because math.pi is not an exact perfect PI value!)
        phase, cycleNum = math.modf(n / samplesPerCycle + phaseOffsetCycles)
        yield peakValue * math.sin(phase * 2 * math.pi)
        n=n+1



def genBeepSequence(beepCentreTimesSecs, idealBeepDurationSecs, sequenceDurationSecs, sampleRateHz, toneHz, amplitude):
    """\
    Generates the audio sample values needed to create audio data containing beeps corresponding to the timings specified.
    
    :param beepCentreTimeSecs: A list or iterable of the centre times of each beep (in seconds since the beginning of the sequence)
    :param idealBeepDurationSecs: ideal duration of a beep in seconds
    :param sequenceDurationSecs: total sequence duration in seconds
    :param sampleRateHz: The final output sample rate in Hz
    :param toneHz: The tone frequence in Hz for the beeps
    :param amplitude: The peak amplitude for the beeps
    
    :returns: An iterable that generates the sample values starting with the first sample value
    """
    beepDurationSamples = calcNearestDurationForExactNumberOfCycles(idealBeepDurationSecs, toneHz)
    
    beepStartEndSamples = genSequenceStartEnds(beepCentreTimesSecs, beepDurationSamples, 1.0, sampleRateHz)

    nSamples = sequenceDurationSecs * sampleRateHz

    def toneGenFactory():
        return GenTone(sampleRateHz, amplitude, toneHz, 0.0)
        
    def silenceGen():
        while True:
            yield 0.0
        
    seqIter = genSequenceFromSampleIndices(beepStartEndSamples, silenceGen, toneGenFactory)
    
    return itertools.islice(seqIter, 0, nSamples)



def secsToSamples(tSecs, startSample=0, sampleRateHz = 480000):
    return secsToTicks(tSecs, startSample, sampleRateHz)


