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
Example master TV measurement system / tester
=======================================

Purpose and Usage
-----------------

This is an example command line tool that runs a measurement system, acting in
the role of the CSA, to check the synchronisation timing of a master TV that
it connects to. The measurements are taken by an Arduino Due microcontroller
connected via USB and with light sensor(s) and audio input(s) connected. These
observe the pattern of flashes/beeps from a test video sequence played by the
TV.

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
centre point timings.

We instantiate a CSS-WC client and a CSS_TS client here.

The wall clock client will communicate with a wall clock server (specified by the cmd) line using
the CSS-WC protocol so that the local wall clock value approximates closely to the remote value of the server's wall clock
at any instant of time here in the measuring system.

The TV master is rendering video content.  In the general case (not handled in this system), that content
could be available on the TV via different timelines (e.g from the broadcast transport stream, in which
case the timeline is expressed using presentation time stamps; or it could come e.g. from a catch-up
service, in which the timeline is expressed using whatever has been used to encode the catch-up
video delivered over IP).

Using the CSS-TS protocol, the client (here) requests the content by its id (actually by a content
stem) and which timeline to try and find for it (command line arguments)

Assuming the TV is rendering this content using this
timeline, then the CSS-TS master on the TV creates a control timestamp, which measures both the
value of the timeline clock and the value of the wallclock at that instant in time, which is
sent to the client.  Assuming the TV is correctly rendering the content, there is a linear relationship
between its timeline clock and its wallclock ... the control timestamp provides a point on this line.
Used in conjunction with the timeline speed multiplier (1.0 for normal playback), which provides the slope of this line,
we can therefore calculate what the value of the timeline clock should be using our local wallclock (which tracks the
remote wallclock, and adjusts as needed based on CSS-WC information).

This is handled by a local clock object, a CorrelatedClock whose tick rate is set to match that
of the requested timeline (command line parameter).  This clock is correlated with the local wallclock.

Any adjustment needed to the local wallclock (based on observing the CSS-WC protocol) will cause the
correlated clock to adjust, and in turn this causes a response in a TSClientClockController object,
resulting in a new control timestamp being reported to the measuring system (actually within measurer.py)

Any such changes are remembered, along with changes of dispersion in the wallclock, picked up
by the local wallclock's algorithm, and these are available to reconstitute the changes in timeline/
wallclock relationship occurring during the data capture.

We know, from the command line, the starting value of the timeline.  We also know the relationship
between the arduino due's clock and our local wall clock ... this means we can capture the flashes/beeps
and compute the correspond timeline clock value, based on the remembered control timestamp information
and the remembered dispersion data.

These can be compared against the expected times provided by the json file.


The overall process is:

    Parse the command line.

    Create a wall clock client, and a CSS-TS client, the CorrelatedClock
    with the same tick rate as the timeline, and the TSClientClockController.
    Create a dispersion recorder hooked up to the wallclock algorithm.



    Create the servers for the CSS-CII, WC and TS protocols using parsed command line.

    Create the synchronisation timeline whose control timestamps will be served to the CSA.

        The sync timeline has an associated clock whose tick rate is a command line argument

    Create a Measurer object

        The constructor connects to the Arduino and sends it commands to indicate which
        light-sensor and audio inputs are to be sampled

    Provide the Measurer with the TSClientClockController so that the measurer can hook
    into the controller to get notification of changes in the timeline behaviour reported
    over CSS_TS.

    Start up the clients (wallclock and TSClientClockController).  These will attempt to connect
    to their servers, and timeout if unsuccessful.

    Wait for the operator to indicate when the client device under test is ready.

        For example, a few seconds of test video clip may have already played before
        the operator arranged for the device under test to attempt to
        synchronise and hence get paused because the test system has sent an initial pause
        command over the CSS-TS protocol.


    The measurer object then starts the capture (it is given the dispersion recorder to
    use during the capture).

        It sends the data capture command to the arduino, which eventually returns once its sample
        buffer is full.  The arduino returns the captured data along with precise timings
        for the start and end of this capture.

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
from dispersion import DispersionRecorder
import stats




def createCSSClientObjects(cmdParser):
    """\

    Create the client objects needed to engage in the CSS-WC and CSS-TS protocols.
    :param cmdParser the command line parser object

    """
    args = cmdParser.args
    sysclock=SysClock()
    wallClock=TunableClock(sysclock,tickRate=1000000000) # nanos
    # measure precision of wall clock empirically
    wcPrecisionNanos = measurePrecision(wallClock) * 1000000000
    algorithm = LowestDispersionCandidate(wallClock,repeatSecs=0.3,timeoutSecs=0.3)
    wcClient=WallClockClient(cmdParser.wcBind, args.wcUrl[0], wallClock, algorithm)
    timelineClock = CorrelatedClock(wallClock, args.timelineClockFrequency)

    # start recording dispersion of the wall clock
    dispRecorder=DispersionRecorder(algorithm)
    dispRecorder.start()

    print "Connecting, requesting timeline for:"
    print "   Any contentId beginning with:", args.contentIdStem
    print "   and using timeline selector: ", args.timelineSelector
    print

    ts = TSClientClockController(args.tsUrl[0], args.contentIdStem, args.timelineSelector, timelineClock, correlationChangeThresholdSecs=0.0)
    return (ts, timelineClock, args.timelineClockFrequency, wcClient, wallClock, wcPrecisionNanos, dispRecorder)


def startCSSClients(wallClockClient, tsClientClockController):
    """\

    Start the wallclock and TS client clock controller.  The CSS protocols
    commence.

    """
    wallClockClient.start()
    tsClientClockController.connect()






if __name__ == "__main__":

    from testsetupcmdline import TVTesterCmdLineParser

    import time

    cmdParser = TVTesterCmdLineParser()
    cmdParser.setupArguments()
    cmdParser.parseArguments()
    cmdParser.printTestSetup()

    syncTimelineClockController, \
    syncTimelineClock, \
    syncClockTickRate, \
    wallClockClient, \
    wallClock, \
    wcPrecisionNanos, \
    dispRecorder = createCSSClientObjects(cmdParser)

    # Arduino Due micros() function precision known to be 1us
    # http://forum.arduino.cc/index.php?PHPSESSID=dulptiubbkqqer7p5hv2fqc583&topic=147505.msg1108517#msg1108517
    acPrecisionNanos = 1000

    CONNECT_TIMEOUT = 10.0
    TIMELINE_AVAILABLE_TIMEOUT = 5.0

    # once clients are started, need to catch keyboard interrupt to close them
    # down in event of ctrl-c to exit the app
    try:

        measurer = Measurer("client", \
                            cmdParser.pinsToMeasure, \
                            cmdParser.pinExpectedTimes, \
                            cmdParser.pinEventDurations, \
                            cmdParser.args.videoStartTicks, \
                            wallClock, \
                            syncTimelineClock, \
                            syncClockTickRate, \
                            wcPrecisionNanos, \
                            acPrecisionNanos, \
                            cmdParser.measurerTime)

        measurer.setSyncTimeLinelockController(syncTimelineClockController)

        print "Connecting..."
        startCSSClients(wallClockClient, syncTimelineClockController)

        # wait for a few seconds as we try to connect to CSS-TS
        timeout = time.time() + CONNECT_TIMEOUT
        while not syncTimelineClockController.connected and time.time() < timeout:
            time.sleep(0.1)
        if not syncTimelineClockController.connected:
            sys.stderr.write("\nTimed out trying to connect to CSS-TS. Aborting.\n\n")
            sys.exit(1)

        print "Connected."

        # check we're receiving control timestamps for a valid timeline
        print "Syncing to timeline..."
        timeout = time.time() + TIMELINE_AVAILABLE_TIMEOUT
        while not syncTimelineClockController.timelineAvailable and time.time() < timeout:
            time.sleep(0.1)
        if not syncTimelineClockController.timelineAvailable:
            sys.stderr.write("\n\nWaited a while, but timeline was not available. Aborting.\n\n")
            sys.exit(1)

        print "Synced to timeline."

        # finally check if dispersion is sane before proceeding
        currentDispersion = wallClockClient.algorithm.getCurrentDispersion()
        if currentDispersion > 1000000000*1.0:
            sys.stderr.write("\n\nWall clock client synced with dispersion +/- %f.3 milliseconds." % (currentDispersion / 1000000.0))
            sys.stderr.write("\nWhich is greater than +/- 1 second. Aborting.\n\n")
            sys.exit(1)


        print
        print "Beginning to measure"
        measurer.capture()

        # sanity check we are still connected to the CSS-TS server
        if not syncTimelineClockController.connected and syncTimelineClockController.timelineAvailable:
            sys.write("\n\nLost connection to CSS-TS or timeline became unavailable. Aborting.\n\n")
            sys.exit(1)

        measurer.detectBeepsAndFlashes(dispersionFunc = dispRecorder.dispersionAt)

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
