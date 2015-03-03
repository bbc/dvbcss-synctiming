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
This python library handles communication with the Arudino Due microcontroller
via its "native" USB port. The arduino must be running the code supplied in
the "hardware" directory of this project.

Requires 'pyserial' (can be installed from the python package index using PIP).


Usage
-----

The :func:`connect` function returns a handle to a file object for communicating with
the Arduino.

The following functions are then used to control the Arduino:

* :func:`samplePinDuringCapture` ... enable one of the input pins to be captured
* :func:`prepareToCapture`       ... query the arduino to find out how much data will be captured
* :func:`capture`                ... initiate sampling of the enabled input pins
* :func:`bulkTransfer`           ... retrieve captured data

Once you have finished communicating with the Arduino, just close the file
handle.

All these functions require that you pass a :mod:`dvbcss.clock` object as well
as the file handle. This is because a simple NTP request-response style time
synchronisation measurement is performed for every command that is sent.

It is this process that makes it possible to translate the time the arduino
reports that it started and finished sampling into a time relevant to the
PC running this python code.



Internals
---------

Some constants are defined that contain the string to be sent to
give the Arduino a particular command.

* CMD_BULK
* CMD_CAPTURE
* CMD_PREPARE_TO_CAPTURE
* CMD_TIMEONLY

Various functions in this module will parse bytes received via the file handle
appropriate to the particular command used. Some functions will also send
the command. See individual documentation for each.



"""

import sys
import re

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    sys.stderr.write("Needs pyserial library. Install with PIP, e.g.:\n\n")
    sys.stderr.write("    sudo pip install pyserial\n\n")
    sys.exit(1)




# -----------------------------------------------------------------------------
#   INTERNALS
# -----------------------------------------------------------------------------


# ----- COMMANDS ----------------------------------------------------------
# send these commands by using f.write(..) on your file handle for the arduino


CMD_BULK = "B"
CMD_CAPTURE = "S"
CMD_PREPARE_TO_CAPTURE = "4"
CMD_TIMEONLY = "T"
CMDS_ENABLE_PIN = [ '0', '1', '2', '3' ]

# -----------------------------------------------------------------------------



def getInt(f):
    """\
    Read a 4 byte integer sent by the Arduino

    :param f: file handle for the serial connection to the Arduino Due
    
    :returns value: 32-bit unsigned integer (read as 4 bytes, most significant byte first)
    """
    n=f.read(4)
    v = (ord(n[0])<<24) + (ord(n[1])<<16) + (ord(n[2])<<8) + ord(n[3])
    return v


def getIntWithTime(f, clock):
    """\
    Read a 4 byte integer sent by the Arduino and report the clock tick valueat which the read completed.

    :param f: file handle for the serial connection to the Arduino Due
    :param clock: a :class:`dvbcss.clock` clock object
    
    :returns (value, ticks): A tuple containing the read 32-bit unsigned integer (see :func:`getInf`) and the tick value of the supplied clock object
    """
    n=f.read(4)
    t4 = clock.ticks
    v = (ord(n[0])<<24) + (ord(n[1])<<16) + (ord(n[2])<<8) + ord(n[3])
    return v, t4


def writeCmdAndTimeRoundTrip(f, clock, cmd):
    """\ 
    Send a command byte to the Arduino, and return a 4-tuple reflecting local
    and arduino times measured for round trip.
    
    :param f: file handle for the serial connection to the Arduino Due
    :param clock: a :class:`dvbcss.clock` clock object
    :param cmd: The command to send to the ARduino.
    
    We measure the value of clock.tick just prior to sending the command byte.
    The Arduino measures its local time (using its micros() function) as soon as data is available on
    the serial USB port. It immediately sends that time back, flushing the serial USB port, then reads
    the command byte.
    
    We read that time value sent by the arduino, and immediately read the supplied clock object again.
    
    :returns (t1,t2,t3,t4): Where t1 and t4 are in terms of the supplied clock object and t2 and t3 are from the Arduino.
    
    Where:
    * t1 is the clock.ticks value from just before the command was sent
    * t2 and t3 are the arduino micros() time value from when the comand was received
    * t4 is the clock.ticks value from just after the response was received from the Arduino.
    
    All returned Ardinio time values are in units of nanoseconds. The clock object times are in units of ticks of that clock.
    """
    t1 = clock.ticks
    f.write(cmd)
    arduinoArrivalTime, t4 = getIntWithTime(f, clock)
    # convert to nanosecs
    arduinoArrivalTime *= 1000
    return [t1, arduinoArrivalTime, arduinoArrivalTime, t4]


# -----------------------------------------------------------------------------
# FUNCTIONS INTENDED FOR USE BY CODE USING THIS MODULE
# -----------------------------------------------------------------------------


def connect():
    """\
    Connect to Arduino via serial and return a file handle for communicating with it.
    
    :returns: file handle for the serial connection
    
    :raises RuntimeError: if unable to detect a connected Arduino Due
    """
    for (COMMS_CHANNEL, NAME, deviceId) in serial.tools.list_ports.comports():
        if re.match(r"^\s*USB VID:PID=0*2341:0*3e\b", deviceId, re.I):
            f = serial.Serial(COMMS_CHANNEL, 115200, timeout=60)
            return f
    raise RuntimeError("Could not locate arduino serial port connection. Arduino not plugged in? Or plugged into wrong serial port on the arduino?")



def prepareToCapture(f, clock):
    """\
    Retrieve information from the arduino on what will be captured if :func:`capture` is called.
    
    :param f: file handle for the serial connection to the Arduino Due
    :param clock: a :class:`dvbcss.clock` clock object

    The Arduino then computes the number of blocks of data the arduino will collect during capture(),
    initialises this data area, and writes back :
    
    1) The number of pins its going to be reading during capture()
    as determined by prior calls to samplePinDuringCapture()
    
    2) The number of data blocks that will be captured during capture().  One data block
    holds the observed high and low values sampled for all enabled pin during one millisecond.
    See :func:`capture` for the format of these blocks.
    
    :returns: tuple (nActivePorts, nMilliBlocks, timingData)
    
    The return tuple contains:
    * the number of analogue pins that will be read (-1 means there's a problem),
    * the number of milliseconds that will be sampled,
    * round-trip timing data
    
    See :func:`writeAndTimeRoundTrip` for details of the meaning of the returned round-trip timing data
    
    """
    # send the cmd "4" ... chr(4 + 48)
    timeData = writeCmdAndTimeRoundTrip(f, clock, CMD_PREPARE_TO_CAPTURE)
    nActivePorts = getInt(f)
    nMilliBlocks = getInt(f)
    return nActivePorts, nMilliBlocks, timeData
 
    
def samplePinDuringCapture(f, pin, clock):
    """\
    Configure Arduino to enable sampling of a particular light sensor or audio
    signal input pin. Only enabled pins are read when capture() is subsequently called.
    
    :param f: file handle for the serial connection to the Arduino Due
    :param pin: The pin to enable.
    :param clock: a :class:`dvbcss.clock` clock object
    
    Values for the pin parameter:
    * 0 enables reading of light sensor 0 (on Arduino analogue pin 0).
    * 1 enables reading of audio input 0 (on Arduino analogue pin 1).
    * 2 enables reading of light sensor 1 (on Arduino analogue pin 2).
    * 3 enables reading of audio input 1 (on Arduino analogue pin 3).

    :returns: (t1,t2,t3,t4) measuring the specified clock object and arduino clock, as per :func`writeCmdAndTimeRoundTrip`

    See :func:`writeAndTimeRoundTrip` for details of the meaning of the returned round-trip timing data
    
    """
    CMD = CMDS_ENABLE_PIN[pin]
    return writeCmdAndTimeRoundTrip(f, clock, CMD)



def capture(f, clock):
    """\
    Instruct the arduino to start capturing sample data.
    
    This function returns information about the capturing process (when capturing
    began and ended, and how many millisecond samples were captured).
    
    Afterwards, you must call bulkTransfer() to retrieve the sample data itself.
    
    :param f: file handle for the serial connection to the Arduino Due
    :param clock: a :class:`dvbcss.clock` clock object
    
    
    
    The number of millisecond blocks the Arduino captures
    depends how many pins are requested to be sampled (see samplePinDuringCapture() ).  
   
    One millisecond block will hold the high and low values sampled
    for each pin, within one millisecond.  With 4 pins enabled, one
    millisecond block will hold 8 bytes.
   
    Each pin's data contributes 2 bytes per block.  
   
    One pin's data block is stored in ascending byte addresses
    as "high" value, then "low" value, as observed over a millisecond.  
   
    For each enabled pin, the data blocks within the millisecond block are organised so that, if pin A < pin B,
    A's data block appears before B's in the millisecond block.
   
    In response, the arduino reads the local time (using micros) and remembers this microsecond value as the start time
    and immediately starts capturing the sample data.
   
    Once complete, the finish time (in microseconds) is measured.
   
    The Arduino then sends back the start time when data capture commenced,
    followed by the finish time, followed by the number of millisecond blocks captured.
   
    :returns tuple (startTime, finishTime, nMilliblocks, preStartTimingData, postFinshTimingData)
    
    The return tuple contains:
    * Arduino clock time (in nanoseconds) when sampling commenced, 
    * Arduino clock time (in nanoseconds) when sampling ended, 
    * The number of millisecond of data sampled
    * The round-trip the timing data (t1,t2,t3,t4) when capture command was sent to the Arduino
    * The round-trip the timing data (t1,t2,t3,t4) just after the sampling finished
   
    See :func:`writeAndTimeRoundTrip` for details of the meaning of the returned round-trip timing data
    """
    
    timeDataPre = writeCmdAndTimeRoundTrip(f, clock, CMD_CAPTURE)
    
    # retrieve the times the Arduino says it started and finished sampling
    # and normalise to nanoseconds (from microseconds)
    dueStartBoundary = getInt(f) * 1000
    dueFinished = getInt(f) * 1000
        
    # retrieve the count of the number of millisecond blocks the Arduino says it sampled
    nMilliBlocks = getInt(f)
    timeDataPost = writeCmdAndTimeRoundTrip(f, clock, CMD_TIMEONLY)
    
    # watch out for any wrapping of the arduino clock ... unlikely but possible
    if timeDataPre[2] < timeDataPre[1]:
        timeDataPre[2] += (1000 * (2 ** 32))
    
    if dueStartBoundary < timeDataPre[2]:
        dueStartBoundary += (1000 * (2 ** 32))
        
    if dueFinished < dueStartBoundary:
        dueFinished += (1000 * (2 ** 32))
    
    if timeDataPost[1] < dueFinished:
        timeDataPost[1] += (1000 * (2 ** 32))
    
    if timeDataPost[2] < timeDataPost[1]:
        timeDataPost[2] += (1000 * (2 ** 32))
    
    return dueStartBoundary, dueFinished, nMilliBlocks, timeDataPre, timeDataPost



def bulkTransfer(f, clock):
    """\
    Request the Arduino send the captured sample data blocks and return them.
    
    :param f: file handle for the serial connection to the Arduino Due
    :param clock: a :class:`dvbcss.clock` clock object
    
    The arduino transfers the microsecond blocks it's created during the most
    recent call to :func:`capture`. The data is formatted as a single string
    containing the raw bytes of sample data.
    
    :returns tuple (numSamples, (rawSampleData, timingData))

    See :func:`writeAndTimeRoundTrip` for details of the meaning of the returned round-trip timing data

    """
    timeData = writeCmdAndTimeRoundTrip(f, clock, CMD_BULK)
    n = getInt(f)
    samples = f.read(n)
    return samples, timeData   


   
if __name__=="__main__":
    print "This is a library of functions for communicating with the arduino"
    print "for timing reference-point calibration for video and audio."
    print
    print "See source code for documentation"
    print
