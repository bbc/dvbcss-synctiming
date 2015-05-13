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


import cherrypy
import sys
import time

from ws4py.server.cherrypyserver import WebSocketPlugin
from dvbcss.protocol.server.cii import CIIServer

from dvbcss.protocol.server.wc import WallClockServer
from dvbcss.protocol.cii import TimelineOption
from dvbcss.clock import SysClock, CorrelatedClock, measurePrecision
from dvbcss.protocol.server.ts import TSServer, SimpleClockTimelineSource

from measurer import Measurer
from measurer import DubiousInput
import stats




# bind it to the URL path /cii in the cherrypy server
class Root(object):
    @cherrypy.expose
    def cii(self):
        pass

    @cherrypy.expose
    def ts(self):
        pass


def exposeWebSocketsViaCherrypy(ciiServer, tsServer):
    # construct the configuration for this path, providing the handler and turning on the tool hook
    cfg = {"/cii": {'tools.dvb_cii.on': True,
                    'tools.dvb_cii.handler_cls': ciiServer.handler
                   },
           "/ts":  {'tools.dvb_ts.on': True,
                    'tools.dvb_ts.handler_cls': tsServer.handler
                   }
          }
    cherrypy.tree.mount(Root(), "/", config=cfg)


def setupWallClockMaster(maxFreqError, addr, port):
    wallClock=SysClock(tickRate=1000000000)
    precisionSecs=measurePrecision(wallClock)
    wcServer=WallClockServer(wallClock, precisionSecs, maxFreqError, addr, port)
    return (wcServer, wallClock, precisionSecs)


def setupCIIAndTSMasters(wclock, contentId, timelineSelector, unitsPerTick, unitsPerSecond):
    """\

    initialise the web socket plugin for cherrypy, and createthe CII and TS servers
    servers, with initial message state. Hook both the server handlers
    into the cherrypy framework so they will get called when clients connect
    to the respective /cii and /ts web socket resources

    """
    # initialise the ws4py websocket plugin
    WebSocketPlugin(cherrypy.engine).subscribe()
    # create CII Server
    ciiServer = CIIServer(maxConnectionsAllowed=2)
    setInitialCII(ciiServer, contentId, timelineSelector, unitsPerTick, unitsPerSecond)
    tsServer = TSServer(contentId=ciiServer.cii.contentId, wallClock=wclock, maxConnectionsAllowed=3)
    exposeWebSocketsViaCherrypy(ciiServer, tsServer)
    return (ciiServer, tsServer)


def startWebSocketServices(host,port):
    """\

    start up cherrypy framework.  TS and CII clients will be able to connect once started
    and receive initial state messages

    """

    # configure cherrypy to serve on port 7681
    cherrypy.config.update({"server.socket_host": host})
    cherrypy.config.update({"server.socket_port":port})
    cherrypy.config.update({"engine.autoreload.on":False})
    # activate cherrypy web server (non blocking).
    # on return, both the CII and TS servers are running, accessible via their resources (/cii and /ts)
    # as soon as clients(s) connect, they'll get the first CII or TS message in response.
    cherrypy.engine.start()


def setInitialCII(ciiServer, contentId, timelineSelector, unitsPerTick, unitsPerSecond):
    """\

    create the initial CII state that will get sent to CII clients when they connect
    test harness will not change these CII properties again, though a real TV would update
    them as the user changes to a different service, or a new DVB event occurs on same service

    """
    ciiServer.cii.protocolVersion = "1.1"
    ciiServer.cii.contentId = contentId # "urn:uk.co.bbc.rd:companion-screen:test-calibration-stream"
    ciiServer.cii.contentIdStatus = "final"
    ciiServer.cii.presentationStatus = "okay"

    t1 = TimelineOption(timelineSelector=timelineSelector, unitsPerTick=unitsPerTick, unitsPerSecond=unitsPerSecond)
    ciiServer.cii.timelines = [t1]



def makeTSServerObjects(tsServer, wallClock, timelineSelector, tickRate, startTickValue):
    """\

    create a clock with tick rate, and correlated with wall clock to be paused at the intended start value.
    create a time line source, that uses the wall clock and timeline clock for creating time stamps to
    be sent by the TS server on demand of the harness (by calling sendTSMessage).
    attach that time line to the TS server.  No messages are sent over TS protocol until
    client(s) are connected, and only then when sendTSMessage() is called by the harness

    """
    syncClock=CorrelatedClock(parentClock=wallClock, tickRate=tickRate)
    syncClock.speed = 0
    syncClock.correlation = (wallClock.ticks, startTickValue)
    pauseSyncTimelineClock(syncClock)

    # Once added to the TS server, the timeline is available for clients to request via the server
    # for TS messages from this type of timeline, if it exists for the CI stem sent by the TS client.
    # normally this CI stem matches a substring of the CII-delivered contentId.
    syncTimelineSrc = SimpleClockTimelineSource(timelineSelector=timelineSelector, wallClock=wallClock, clock=syncClock)
    tsServer.attachTimelineSource(syncTimelineSrc)
    return syncClock



def createServers(args):
    """\

    create the wall clock, the CSS-WC  server, the CSS-TS server, and the CSS-CII server

    :param args
                args.addr[0] is host address for servers
                args.portwc[0] is the WC server port
                args.portwebsocket[0] is the web socket port via which CII and TS server access occurs
    :returns tuple (wcServer instance, tsServer instance, wallClock instance,
                    wcUrl, ciiUrl, tsUrl)

    """

    wcUrl = "udp://" + args.addr[0] + ":" + str(args.portwc[0])
    ciiUrl = "ws://" + args.addr[0] + ":" + str(args.portwebsocket[0])  + "/cii"
    tsUrl = "ws://" + args.addr[0] + ":" + str(args.portwebsocket[0])  + "/ts"

    wcServer, wallClock, precisionSecs = setupWallClockMaster(args.maxFreqError, args.addr[0], args.portwc[0])
    ciiServer, tsServer = setupCIIAndTSMasters(wallClock, args.contentId, args.timelineSelector, args.unitsPerTick, args.unitsPerSec)
    ciiServer.cii.wcUrl = wcUrl
    ciiServer.cii.tsUrl = tsUrl

    return {
        "wcServer":(wcServer, wcUrl), "tsServer": (tsServer, tsUrl),
        "ciiServer": (ciiServer, ciiUrl), "wallclock": wallClock,
        "wallclockPrecisionSecs" : precisionSecs
    }


def startServers(args, wcServer):
    """\

    start the CSS-WC  server, the CSS-TS server, and the CSS-CII server

    :param args
                args.addr[0] is host address for servers
                args.portwc[0] is the WC server port
                args.portwebsocket[0] is the web socket port via which CII and TS server access occurs
    :param wcServer the wall clock server

    """

    wcServer.start()
    startWebSocketServices(args.addr[0], args.portwebsocket[0])


def createTimeline(tsServer, wallClock, args):
    """\

    create the synchronisation timeline whose control time stamps are served to the CSA
    over the CSS-TS protocol.

    :param tsServer the CSS-TS server
    :param wallClock the wall clock whose clock values are sent over the CSS-WC server
    :param args command line arguments, including the units per second and units per tick of the
        sync time line's clock, the starting value for this clock and the time line selector

    """
    tickRate = float(args.unitsPerSec) / float(args.unitsPerTick)
    syncTimelineClock = makeTSServerObjects(tsServer, wallClock, args.timelineSelector, tickRate, args.videoStartTicks)
    return (syncTimelineClock, tickRate)


def pauseSyncTimelineClock(syncClock):
    """\
    Pauses the synchronisation time line clock and adjusts the correlation to make it as if it paused at the current tick value

    :param syncClock: the clock object providing time values for the sync timeline

    """

    syncClock.rebaseCorrelationAtTicks(syncClock.ticks)
    syncClock.speed = 0.0



def unpauseSyncTimelineClock(syncClock):
    """\
    unpauses the synchronisation time line clock and adjusts the correlation with the sync clock's
    parent

    :param syncClock: the clock object providing time values for the sync timeline

    """

    syncClock.correlation = ( syncClock.getParent().ticks, syncClock.correlation[1] )
    syncClock.speed = 1.0

def getWorstCaseDispersionFromDeviceUnderTest():
    """\

    prompt the operator to enter the worst case dispersion value
    observed on the device under test, and return that value

    :returns dispersion value in units of nanoseconds
    """

    print
    dispersion = raw_input("Enter worst case dispersion from CSA seen during measurement (units of milliseconds):")
    return float(dispersion)*1000000.0






if __name__ == "__main__":

    from testsetupcmdline import CsaTesterCmdLineParser

    cmdParser = CsaTesterCmdLineParser()
    cmdParser.setupArguments()
    cmdParser.parseArguments()

    servers = createServers(cmdParser.args)
    cmdParser.printTestSetup(servers["ciiServer"][1], servers["wcServer"][1], servers["tsServer"][1])

    syncTimelineClock, syncClockTickRate = createTimeline(servers["tsServer"][0], servers["wallclock"], cmdParser.args)

    # measure precision of wall clock empirically
    wcPrecisionNanos = servers["wallclockPrecisionSecs"] * 1000000000

    # Arduino Due micros() function precision known to be 1us
    # http://forum.arduino.cc/index.php?PHPSESSID=dulptiubbkqqer7p5hv2fqc583&topic=147505.msg1108517#msg1108517
    acPrecisionNanos = 1000

    startServers(cmdParser.args, servers["wcServer"][0])

    # once servers are started, need to catch keyboard interrupt to close them
    # down in event of ctrl-c to exit the app
    try:
        measurer = Measurer("master", \
                            cmdParser.pinsToMeasure, \
                            cmdParser.pinExpectedTimes, \
                            cmdParser.pinEventDurations, \
                            cmdParser.args.videoStartTicks, \
                            servers["wallclock"], \
                            syncTimelineClock, \
                            syncClockTickRate, \
                            wcPrecisionNanos, \
                            acPrecisionNanos, \
                            cmdParser.measurerTime)

        print
        raw_input("Press RETURN once CSA is connected and synchronising to this 'TV Device' server")

        # let the sync time line clock start ticking and inform any TS clients
        # the CSA will position the playback of the test video and start playing it.
        # At this stage, flashes and beeps are not being captured
        unpauseSyncTimelineClock(syncTimelineClock)
        servers["tsServer"][0].updateAllClients()

        print "Timeline unpaused. Wait for ", cmdParser.args.waitSecs[0], " secs"
        # allow the device under test to settle
        time.sleep(cmdParser.args.waitSecs[0])

        print "Beginning to measure"
        measurer.capture()

        print "Measurement complete. Timeline paused again."
        pauseSyncTimelineClock(syncTimelineClock)
        servers["tsServer"][0].updateAllClients()

        worstCaseDispersion = getWorstCaseDispersionFromDeviceUnderTest()

        def dispersionFunc(wcTime):
            return worstCaseDispersion

        measurer.detectBeepsAndFlashes(dispersionFunc = dispersionFunc)

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
        cherrypy.engine.exit()
        servers["wcServer"][0].stop()


    sys.exit(0)
