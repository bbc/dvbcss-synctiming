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

BaseCmdLineParser contains common arguments to all examples, and sets up a 3
step framework for parsing: init, setupArguments() and parseArguments().

TVTesterCmdLineParser subclasses BaseCmdLineParser adding arguments specific
to exampleTVTester.py

CsaTesterCmdLineParser subclasses BaseCmdLineParser adding arguments specific
to exampleCsaTester.py

"""

import re
import sys
import argparse
import json
import arduino

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


class BaseCmdLineParser(object):
    """\
    Usage:

    1. initialise
    2. call setupArguments()
    3. call parseArguments()

    Parsed arguments will be in the `args` attribute

    Subclass to add more arguments:

      * initialisation puts an argparse.ArgumentParser() into self.parser

      * override setupArguments() to add more arguments - before and/or after
        calling the superclass implementation of setupArguments() to determine
        the order.

      * override parseArguments() to add additional parsing steps. Call the
        superclass implementaiton of parseArguments() first.
    """
    def __init__(self, desc):
        super(BaseCmdLineParser,self).__init__()
        self.parser = argparse.ArgumentParser(description=desc)

        # setup some defaults
        self.PPM=500
        # if no time specified, we'll calculate time based on number of pins
        self.MEASURE_SECS = -1
        self.TOLERANCE = None



    def setupArguments(self):
        """\
        Setup the arguments used by the command line parser.
        Must be called once (and only once) before parsing.
        """

        self.parser.add_argument("timelineSelector", type=str, help="The timelineSelector for the timeline to be used (e.g. \"urn:dvb:css:timeline:pts\" for PTS).")
        self.parser.add_argument("unitsPerTick", type=int, help="The denominator for the timeline tickrate (e.g. 1 for most timelines, such as PTS).")
        self.parser.add_argument("unitsPerSec", type=int, help="The numerator for the timeline tickrate (e.g. 90000 for PTS).")
        self.parser.add_argument("videoStartTicks", type=int, help="The timeline tick value corresponding to when the first frame of the test video sequence is expected to be shown.")
        self.parser.add_argument("--measureSecs",   dest="measureSecs", type=int, nargs=1, help="Duration of measurement period (default is max time possible given number of pins to sample", default=[self.MEASURE_SECS])
        self.parser.add_argument("--light0",   dest="light0_metadatafile", type=str, nargs=1, help="Measure light sensor input 0 and compare to expected flash timings in the named JSON metadata file.")
        self.parser.add_argument("--light1",   dest="light1_metadatafile", type=str, nargs=1, help="Measure light sensor input 1 and compare to expected flash timings in the named JSON metadata file.")
        self.parser.add_argument("--audio0",   dest="audio0_metadatafile", type=str, nargs=1, help="Measure audio input 0 and compare to expected beep timings in the named JSON metadata file.")
        self.parser.add_argument("--audio1",   dest="audio1_metadatafile", type=str, nargs=1, help="Measure audio input 1 and compare to expected beep timings in the named JSON metadata file.")
        self.parser.add_argument("--mfe", \
                        "--maxfreqerror", dest="maxFreqError",  type=int, action="store",default=self.PPM,help="Set the maximum frequency error for the local wall clock in ppm (default="+str(self.PPM)+")")

        self.parser.add_argument("--toleranceTest",dest="toleranceSecs",type=ToleranceOrNone, action="store", nargs=1,help="Do a pass/fail test on whether sync is accurate to within this specified tolerance, in milliseconds. Test is not performed if this is not specified.",default=[self.TOLERANCE])


    def parseArguments(self, args=None):
        """\
        Parse and process arguments.
        :param args: The arguments to process as a list of strings. If not provided, defaults to processing sys.argv
        """

        if args is None:
            self.args = self.parser.parse_args()
        else:
            self.args = self.parser.parse_args(args)


        self.args.timelineClockFrequency = float(self.args.unitsPerSec) / self.args.unitsPerTick

        # dictionary that maps from pin name to json metadata file
        self.pinMetadataFilenames = {
            "LIGHT_0" : self.args.light0_metadatafile,
            "LIGHT_1" : self.args.light1_metadatafile,
            "AUDIO_0" : self.args.audio0_metadatafile,
            "AUDIO_1" : self.args.audio1_metadatafile
        }

        # load in the expected times for each pin being sampled, and also build a list of which pins are being sampled
        self.pinExpectedTimes = _loadExpectedTimeMetadata(self.pinMetadataFilenames)
        self.pinsToMeasure = self.pinExpectedTimes.keys()

        if len(self.pinsToMeasure) == 0:
          sys.stderr.write("\nAborting. No light sensor or audio inputs have been specified.\n\n")
          sys.exit(1)

        # see if the requested time for measuring can be accomodated by the system
        self.measurerTime = arduino.checkCaptureTimeAchievable(self.args.measureSecs[0], len(self.pinsToMeasure))
        if self.measurerTime < 0:
            sys.stderr.write("\nAborting.  The combination of measured time and pins to measure exceeds the measurement system's capabilities.")
            sys.exit(1)

def _loadExpectedTimeMetadata(pinMetadataFilenames):
    """\

    Given an input dictionary mapping pin names to filename, load the
    expected flash/beep times data from the filename and return a dict mapping
    pin names to the expected timing list.

    :param pinMetadataFilenames: dict mapping pin names to either None or a list
       containing a single string which is the filename of the metadata json to load from.

    :returns: dict mapping pin names to lists containing expected flash/beep times
    read from the metadata file. For pins that have a None value, there will be
    no entry in the dict.

    """
    pinExpectedTimes = {}
    try:
        for pinName in pinMetadataFilenames:
            argValue = pinMetadataFilenames[pinName]
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







class TVTesterCmdLineParser(BaseCmdLineParser):

    def __init__(self):

        """\

        parse the command line arguments for the TV testing system

        """
        # defaults for command line arguments
        self.DEFAULT_WC_BIND=("0.0.0.0","random")

        desc = "Measures synchronisation timing for a TV using the DVB CSS protocols. Does this by pretending to be the CSA and using an external Arduino microcontroller to take measurements."
        super(TVTesterCmdLineParser,self).__init__(desc)



    def setupArguments(self):
        # add argument to beginning of list (called before superclass method)
        self.parser.add_argument("contentIdStem", type=str, help="The contentIdStem the measurement system will use when requesting a timeline from the TV, (e.g. \"\" will match all content IDs)")

        # let the superclass add its arguments
        super(TVTesterCmdLineParser,self).setupArguments()

        # add arguments to end of set of arguments (called after superclass method)
        self.parser.add_argument("tsUrl", action="store", type=dvbcss.util.wsUrl_str, nargs=1, help="ws:// URL of TV's CSS-TS end point")
        self.parser.add_argument("wcUrl", action="store", type=dvbcss.util.udpUrl_str, nargs=1, help="udp://<host>:<port> URL of TV's CSS-WC end point")
        self.parser.add_argument("wcBindAddr",action="store", type=dvbcss.util.iphost_str, nargs="?",help="IP address or host name to bind WC client to (default="+str(self.DEFAULT_WC_BIND[0])+")",default=self.DEFAULT_WC_BIND[0])
        self.parser.add_argument("wcBindPort",action="store", type=dvbcss.util.port_int_or_random,   nargs="?",help="Port number to bind WC client to (default="+str(self.DEFAULT_WC_BIND[1])+")",default=self.DEFAULT_WC_BIND[1])


    def parseArguments(self, args=None):
        # let the superclass do the argument parsing and parse the pin data
        super(TVTesterCmdLineParser,self).parseArguments(args)

        self.wcBind = (self.args.wcBindAddr, self.args.wcBindPort)




    def printTestSetup(self):
        """\

        print out the test setup

        """
        print
        print "Scenario setup:"
        for pin in self.pinsToMeasure:
            print "   Measuring input %s using expected timings from : %s" % (pin, self.pinMetadataFilenames[pin][0])
        print
        print "   TS server at                          : %s" % self.args.tsUrl
        print "   WC server at                          : %s" % self.args.wcUrl
        print "   Content id stem asked of the TV       : %s" % self.args.contentIdStem
        print "   Timeline selector asked of TV         : %s" % self.args.timelineSelector
        print
        print "   Assuming TV will be at start of video when timeline at : %d ticks" % (self.args.videoStartTicks)
        print
        print "   When go is pressed, will begin measuring immediately for %d seconds" % self.measurerTime
        print
        if self.args.toleranceSecs[0] is not None:
            print "   Will report if TV is accurate within a tolerance of : %f milliseconds" % (self.args.toleranceSecs[0]*1000.0)
            print




class CsaTesterCmdLineParser(BaseCmdLineParser):


    def __init__(self):

        """\

        parse the command line arguments for the CSA testing system

        """

        # defaults for command line arguments
        self.ADDR="127.0.0.1"
        self.PORT_WC=6677
        self.PORT_WS=7681
        self.WAIT_SECS=5.0

        desc = "Measures synchronisation timing for a Companion Screen using the DVB CSS protocols. Does this by pretending to be the TV Device and using an external Arduino microcontroller to take measurements."
        super(CsaTesterCmdLineParser,self).__init__(desc)


    def setupArguments(self):

        # add argument to beginning of list (called before superclass method)
        self.parser.add_argument("contentId", type=str, help="The contentId the measurement system will pretend to be playing (e.g. \"urn:github.com/bbc/dvbcss-synctiming:sync-timing-test-sequence\")")

        # let the superclass add its arguments
        super(CsaTesterCmdLineParser,self).setupArguments()

        # add arguments to end of set of arguments (called after superclass method)
        self.parser.add_argument("--waitSecs",     dest="waitSecs",      type=float,                  nargs=1, help="Number of seconds to wait before beginning to measure after timeline is unpaused (default=%4.2f)" % self.WAIT_SECS, default=[self.WAIT_SECS])
        self.parser.add_argument("--addr",         dest="addr",          type=dvbcss.util.iphost_str, nargs=1, help="IP address or host name to bind to (default=\""+str(self.ADDR)+"\")",default=[self.ADDR])
        self.parser.add_argument("--wc-port",      dest="portwc",        type=dvbcss.util.port_int,   nargs=1, help="Port number for wall clock server to listen on (default="+str(self.PORT_WC)+")",default=[self.PORT_WC])
        self.parser.add_argument("--ws-port",      dest="portwebsocket", type=dvbcss.util.port_int,   nargs=1, help="Port number for web socket server to listen on (default="+str(self.PORT_WS)+")",default=[self.PORT_WS])


    def parseArguments(self, args=None):
        # let the superclass do the argument parsing and parse the pin data
        super(CsaTesterCmdLineParser,self).parseArguments(args)



    def printTestSetup(self, ciiUrl, wcUrl, tsUrl):
        """\

        print out the test setup

        """

        print
        print "Scenario setup:"
        for pin in self.pinsToMeasure:
            print "   Measuring input %s using expected timings from : %s" % (pin, self.pinMetadataFilenames[pin][0])
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
        print "   ... then unpause the timeline and measure for: %d seconds" % self.measurerTime
        print
        if self.args.toleranceSecs[0] is not None:
            print "   Will report if CSA is accurate within a tolerance of : %f milliseconds" % (self.args.toleranceSecs[0]*1000.0)
            print
