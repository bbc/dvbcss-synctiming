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
Command line parameter parsing classes for the example applications.

"""

import re
import sys
import argparse
import json

import dvbcss.util


def ToleranceOrNone(value):
    """\
    :param value: None, or a string containing a float that is >= 0 representing tolerance in milliseconds
    :returns: None, or tolerance in units of seconds.
    """
    if value is None:
        return None
    else:
        if re.match(r"^[0-9]+(?:\.[0-9]+)?", value):
            return float(value)/1000.0


def createParserWithCommonArgs(desc):
    """\

    create the parser, using the provided description.
    :return the parser

    """

    PPM=500
    #MEASURE_SECS = 15.0
    TOLERANCE = None
    parser=argparse.ArgumentParser(description=desc)
    parser.add_argument("contentId", type=str, help="The contentId the measurement system will pretend to be playing (e.g. \"urn:github.com/bbc/dvbcss-synctiming:sync-timing-test-sequence\")")
    parser.add_argument("timelineSelector", type=str, help="The timelineSelector for the timeline to be provided (e.g. \"urn:dvb:css:timeline:pts\" for PTS).")
    parser.add_argument("videoStartTicks", type=int, help="The timeline tick value corresponding to when the CSA is expected to be showing the first frame of the test video sequence.")
    parser.add_argument("unitsPerTick", type=int, help="The denominator for the timeline tickrate (e.g. 1 for most timelines, such as PTS).")
    parser.add_argument("unitsPerSec", type=int, help="The numerator for the timeline tickrate (e.g. 90000 for PTS).")
    #parser.add_argument("--measureSecs",   dest="measureSecs", type=float, nargs=1, help="Duration of measurement period (default=%4.2f)" % MEASURE_SECS, default=[MEASURE_SECS])
    parser.add_argument("--light0",   dest="light0_metadatafile", type=str, nargs=1, help="Measure light sensor input 0 and compare to expected flash timings in the named JSON metadata file.")
    parser.add_argument("--light1",   dest="light1_metadatafile", type=str, nargs=1, help="Measure light sensor input 1 and compare to expected flash timings in the named JSON metadata file.")
    parser.add_argument("--audio0",   dest="audio0_metadatafile", type=str, nargs=1, help="Measure audio input 0 and compare to expected beep timings in the named JSON metadata file.")
    parser.add_argument("--audio1",   dest="audio1_metadatafile", type=str, nargs=1, help="Measure audio input 1 and compare to expected beep timings in the named JSON metadata file.")
    parser.add_argument("--mfe", \
                        "--maxfreqerror", dest="maxFreqError",  type=int, action="store",default=PPM,help="Set the maximum frequency error for the local wall clock in ppm (default="+str(PPM)+")")

    parser.add_argument("--toleranceTest",dest="toleranceSecs",type=ToleranceOrNone, action="store", nargs=1,help="Do a pass/fail test on whether the CSA is accurately synchronised within this specified tolerance, in milliseconds. Test is not performed if this is not specified.",default=[TOLERANCE])
    return parser


def parsePinArgs(pinArgMap):
    """\

    Parse light/audio input pin selection arguments.

    :param pinArgMap: dict mapping pin names to the corresponding command line
    argument value (as parsed by argparse)

    :returns: dict mapping pin names ("LIGHT_0","LIGHT_1","AUDIO_0","AUDIO_1") to lists containing expected flash/beep times
    read from the metadata file. For pins that are not specified as arguments,
    there will be no entry in the dict.

    """
    pinExpectedTimes = {}
    try:
        for pinName in pinArgMap:
            argValue = pinArgMap[pinName]
            if argValue is not None:
                filename=argValue[0]
                f=open(filename)
                metadata = json.load(f)
                f.close()
                pinExpectedTimes[pinName] = metadata["eventCentreTimes"]
    except IOError:
        sys.stderr.write("\nCould not open one of the specified JSON metadata files.\n\n")
        sys.exit(1)
    except ValueError:
        sys.stderr.write("\nError parsing contents of one of the JSON metadata files. Is it correct JSON?\n\n")
        sys.exit(1)
    return pinExpectedTimes



def createPinArgsMap(args):
    """\

    create the dictionary that maps from pin name to json metadata file
    :returns: the dictionary

    """
    return {
        "LIGHT_0" : args.light0_metadatafile,
        "LIGHT_1" : args.light1_metadatafile,
        "AUDIO_0" : args.audio0_metadatafile,
        "AUDIO_1" : args.audio1_metadatafile
    }


def extractPinData(args):
    """\

    process the command line arguments related to pin inputs to be captured
    :returns: (pinArgMap, pinExpectedTimes, pinsToMeasure)

    """

    pinArgMap = createPinArgsMap(args)
    pinExpectedTimes = parsePinArgs(pinArgMap)
    pinsToMeasure = pinExpectedTimes.keys()
    if len(pinsToMeasure) == 0:
      sys.stderr.write("\nAborting. No light sensor or audio inputs have been specified.\n\n")
      sys.exit(1)
    return (pinArgMap, pinExpectedTimes, pinsToMeasure)





class TVTesterCmdLineParser:

    def __init__(self):

        """\

        parse the command line arguments

        """

        # defaults for command line arguments
        DEFAULT_WC_BIND=("0.0.0.0","random")

        desc = "Measures synchronisation timing for a Master TV using the DVB CSS protocols. Does this by pretending to be the CSA and using an external Arduino microcontroller to take measurements."
        parser = createParserWithCommonArgs(desc)
        parser.add_argument("tsUrl", action="store", type=dvbcss.util.wsUrl_str, nargs=1, help="ws:// URL of TV's CSS-TS end point")
        parser.add_argument("wcUrl", action="store", type=dvbcss.util.udpUrl_str, nargs=1, help="udp://<host>:<port> URL of TV's CSS-WC end point")
        parser.add_argument("wcBindAddr",action="store", type=dvbcss.util.iphost_str, nargs="?",help="IP address or host name to bind WC client to (default="+str(DEFAULT_WC_BIND[0])+")",default=DEFAULT_WC_BIND[0])
        parser.add_argument("wcBindPort",action="store", type=dvbcss.util.port_int_or_random,   nargs="?",help="Port number to bind WC client to (default="+str(DEFAULT_WC_BIND[1])+")",default=DEFAULT_WC_BIND[1])

        self.args = parser.parse_args()
        self.args.timelineClockFrequency =self.args.unitsPerSec/ self.args.unitsPerTick

        wc_dest = self.args.wcUrl[0]
        self.wcBind=(self.args.wcBindAddr, self.args.wcBindPort)

        # parse pin data
        self.pinArgMap, self.pinExpectedTimes, self.pinsToMeasure = extractPinData(self.args)



    def printTestSetup(self):
        """\

        print out the test setup

        """
        print
        print "Scenario setup:"
        for pin in self.pinsToMeasure:
            print "   Measuring input %s using expected timings from : %s" % (pin, self.pinArgMap[pin][0])
        print
        print "   TS server at                          : %s" % self.args.tsUrl
        print "   WC server at                          : %s" % self.args.wcUrl
        print "   Content id stem asked of the TV       : %s" % self.args.contentId
        print "   Timeline selector asked of TV         : %s" % self.args.timelineSelector
        print
        print "   Assuming TV will be at start of video when timeline at : %d ticks" % (self.args.videoStartTicks)
        print
        #print "   When go is pressed, will begin measuring immediately for %f seconds" % self.args.measureSecs[0]
        print "   When go is pressed, will begin measuring immediately."
        print
        if self.args.toleranceSecs[0] is not None:
            print "   Will report if TV is accurate within a tolerance of : %f milliseconds" % (self.args.toleranceSecs[0]*1000.0)
            print




class CsaTesterCmdLineParser:


    def __init__(self):

        """\

        parse the command line arguments

        :param role - "client" or "master"; which role the tester is carrying out in the measurement system

        """

        # defaults for command line arguments
        ADDR="127.0.0.1"
        PORT_WC=6677
        PORT_WS=7681
        WAIT_SECS=5.0

        desc = "Measures synchronisation timing for a Companion Screen using the DVB CSS protocols. Does this by pretending to be the TV Device and using an external Arduino microcontroller to take measurements."
        parser = createParserWithCommonArgs(desc)

        parser.add_argument("--waitSecs",     dest="waitSecs",      type=float,                  nargs=1, help="Number of seconds to wait before beginning to measure after timeline is unpaused (default=%4.2f)" % WAIT_SECS, default=[WAIT_SECS])
        parser.add_argument("--addr",         dest="addr",          type=dvbcss.util.iphost_str, nargs=1, help="IP address or host name to bind to (default=\""+str(ADDR)+"\")",default=[ADDR])
        parser.add_argument("--wc-port",      dest="portwc",        type=dvbcss.util.port_int,   nargs=1, help="Port number for wall clock server to listen on (default="+str(PORT_WC)+")",default=[PORT_WC])
        parser.add_argument("--ws-port",      dest="portwebsocket", type=dvbcss.util.port_int,   nargs=1, help="Port number for web socket server to listen on (default="+str(PORT_WS)+")",default=[PORT_WS])

        self.args = parser.parse_args()

        # parse pin data
        self.pinArgMap, self.pinExpectedTimes, self.pinsToMeasure = extractPinData(self.args)





    def printTestSetup(self, ciiUrl, wcUrl, tsUrl):
        """\

        print out the test setup

        """

        print
        print "Scenario setup:"
        for pin in self.pinsToMeasure:
            print "   Measuring input %s using expected timings from : %s" % (pin, self.pinArgMap[pin][0])
        print
        print "   CII server at                 : %s" % ciiUrl
        print "   TS server at                  : %s" % tsUrl
        print "   WC server at                  : %s" % wcUrl
        print "   Pretending to have content id : %s" % self.args.contentId
        print "   Pretending to have timeline   : %s" % self.args.timelineSelector
        print "   ... with tick rate            : %d/%d ticks per second" % (self.args.unitsPerSec, self.args.unitsPerTick)
        print
        print "   Will begin with timeline at                             : %d ticks" % (self.args.videoStartTicks)
        print "   Assuming CSA will be at start of video when timeline at : %d ticks" % (self.args.videoStartTicks)
        print
        print "   When go is pressed, will wait for            : %f seconds" % self.args.waitSecs[0]
        #print "   ... then unpause the timeline and measure for: %f seconds" % self.args.measureSecs[0]
        print "   ... then unpause the timeline and measure"
        print
        if self.args.toleranceSecs[0] is not None:
            print "   Will report if CSA is accurate within a tolerance of : %f milliseconds" % (self.args.toleranceSecs[0]*1000.0)
            print
