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
Example CSA measurement system / tester
=======================================

Purpose and Usage
-----------------

This is an example command line tool that runs a measurement system, acting in
the role of the TV Device, to check the synchronisation timing of a CSA that
connects to it. The measurements are taken by an Arduino Due microcontroller
connected via USB and with light sensor(s) and audio input(s) connected. These
observe the pattern of flashes/beeps from a test video sequence played by the
CSA.

The final output is a measurement (to the nearest millisecond) of when the
flashes/beeps occurred compared to when they were expected to occur (given the
time line information being conveyed via the protocol).

See the main README.md for more information and example usage.

Use `--help` at the command line for information on arguments.



How it works
------------

This module runs the process of controlling the arduino (activating the appropriate pins for reading),
the sampling of the flashes / beeps, and the detection of the centre point timings of these
and the analysis of these centre points to look for the best match against the expected
centre point timings

The overall process is:

    Parse the command line.

    Create the servers for the CSS-CII, WC and TS protocols using parsed command line.

    Create the synchronisation timeline whose control timestamps will be served to the CSA.

        The sync timeline has an associated clock whose tick rate is a command line argument

    Start the servers

    Create a Measurer object

        The constructor connects to the Arduino and sends it commands to indicate which
        light-sensor and audio inputs are to be sampled

    Wait for the operator to indicate when the client device under test is ready.

        For example, a few seconds of test video clip may have already played before
        the operator arranged for the device under test to attempt to
        synchronise and hence get paused because the test system has sent an initial pause
        command over the CSS-TS protocol.

    Once the operator informs the test system to continue, the sync timeline is unpaused,

    This unpausing causes a snapshot to be taken of the wall clock and corresponding sync time line clock
    that the CSS_TS server passes this on to the CSA.

    In response The CSA synchronises its video play back in accordance with the control timestamp it receives.
    The CSA adjusts the play back position within the test video and starts playing it.

    The measuring system is not yet enabled to capture the flashes and beeps.

    This python thread sleeps for some time (cmd line argument) to allow the video playback to settle (e.g. there may be
    repositioning of the video initially once synchronised(.

    The measurer object then starts the capture.

        It sends the data capture command to the arduino, which eventually returns once its sample
        buffer is full.  The arduino returns the captured data along with precise timings
        for the start and end of this capture.

    The we pause the sync time line (sets the speed to 0.0) informing the CSA under test
    over CSS_TS protocol.

    The operator is prompted to enter the worst case wall clock dispersion for the CSA (the CSA could
    intermittently print out the dispersion).

    This dispersion value is passed to the measurer object.

    The measurer then examines the captured data to find the times of the centre points of the beeps and/or flashes
    across the channels of data received (one channel per pin).

    Finally, the timing for each channel is analysed to find the best match of these centre points (the observed data)
    against the expected timings for the video clip and statistics generated.


'''


import sys
import time

from ws4py.server.cherrypyserver import WebSocketPlugin
from dvbcss.protocol.cii import TimelineOption
from dvbcss.clock import SysClock, CorrelatedClock, measurePrecision, TunableClock
from dvbcss.protocol.client.wc.algorithm import LowestDispersionCandidate
from dvbcss.protocol.client.wc import WallClockClient
from dvbcss.protocol.client.ts import TSClientClockController


from measurer import Measurer
from measurer import DubiousInput
import stats




def createCSSClientObjects(cmdParser):
    args = cmdParser.args
    sysclock=SysClock()
    wallClock=TunableClock(sysclock,tickRate=1000000000) # nanos
    # measure precision of wall clock empirically
    wcPrecisionNanos = measurePrecision(wallClock) * 1000000000
    algorithm = LowestDispersionCandidate(wallClock,repeatSecs=0.3,timeoutSecs=0.3)
    wcClient=WallClockClient(cmdParser.wcBind, args.wcUrl[0], wallClock, algorithm)
    timelineClock = CorrelatedClock(wallClock, args.timelineClockFrequency)

    print "Connecting, requesting timeline for:"
    print "   Any contentId beginning with:", args.contentIdStem
    print "   and using timeline selector: ", args.timelineSelector
    print

    ts = TSClientClockController(args.tsUrl[0], args.contentIdStem, args.timelineSelector, timelineClock, correlationChangeThresholdSecs=0.0)
    return (ts, timelineClock, args.timelineClockFrequency, wcClient, wallClock, wcPrecisionNanos)


def getWorstCaseDispersion():
    """\

    prompt the operator to enter the worst case dispersion value
    observed on the device under test, and return that value

    :returns dispersion value in units of nanoseconds
    """

    print
    dispersion = 1.9
    return float(dispersion)*1000000.0


def startCSSClients(wallClockClient, tsClientClockController):
    wallClockClient.start()
    tsClientClockController.connect()




if __name__ == "__main__":

    from testsetupcmdlineForTVTester import TVTesterCmdLineParser

    cmdParser = TVTesterCmdLineParser()
    cmdParser.printTestSetup()

    syncTimelineClockController, \
    syncTimelineClock, \
    syncClockTickRate, \
    wallClockClient, \
    wallClock, \
    wcPrecisionNanos = createCSSClientObjects(cmdParser)

    # Arduino Due micros() function precision known to be 1us
    # http://forum.arduino.cc/index.php?PHPSESSID=dulptiubbkqqer7p5hv2fqc583&topic=147505.msg1108517#msg1108517
    acPrecisionNanos = 1000

    # once clients are started, need to catch keyboard interrupt to close them
    # down in event of ctrl-c to exit the app
    try:

        measurer = Measurer("client", \
                            cmdParser.pinsToMeasure, \
                            cmdParser.pinExpectedTimes, \
                            cmdParser.args.videoStartTicks, \
                            wallClock, \
                            syncTimelineClock, \
                            syncClockTickRate)

        measurer.setSyncTimeLinelockController(syncTimelineClockController)

        startCSSClients(wallClockClient, syncTimelineClockController)


        print
        print "Beginning to measure"
        measurer.capture()

        worstCaseDispersion = getWorstCaseDispersion()
        measurer.packageDispersionData(worstCaseDispersion)

        measurer.detectBeepsAndFlashes(wcPrecisionNanos, acPrecisionNanos)

        for channel in measurer.getComparisonChannels():
            try:
                index, expected, timeDifferencesAndErrors = measurer.doComparison(channel)

                print
                print "Results for channel: %s" % channel["pinName"]
                print "----------------------------"
                stats.calcAndPrintStats(index, expected, timeDifferencesAndErrors, cmdParser.args.toleranceSecs[0])

            except DubiousInput:

                print
                print "Cannot reliably measure on pin: %s" % channel["pinName"]
                print "Is input plugged into pin?  Is the input level is too low?"

    except KeyboardInterrupt:
        pass

    finally:
        pass


    sys.exit(0)
