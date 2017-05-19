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
Synchronisation timing measurement test sequence generator.

This program generates a WAV files and PNG files for the video frames making
up a test sequence that can be used to measure synchronisation timing.

Use ``--help`` for command line options.

The program also outputs a file containing a list of the timings of the
beeps and flashes in a variety of units (seconds, milliseconds, frames, and
PTS for MPEG transport stream).

The "beeps" and "flashes" are co-incident and so can be used to check AV
alignment.

Comparing the behaviour of a media playback device against the timing data will
also allow you to measure how well synchronised that media playback is to
a source of timing control information (e.g. Control Timestamps passed via
the DVB protocols for companion screen synchronisation).

The pattern of timings of beeps and flashes are such that for a minimum duration
period of observation, you will not see the same pattern of timings of
beeps/flashes anywhere else in the sequence.

"""

from eventTimingGen import mls, _mls_taps
from eventTimingGen import encodeBitStreamAsPulseTimings
from eventTimingGen import calcNearestDurationForExactNumberOfCycles
from eventTimingGen import genSequenceStartEnds
from eventTimingGen import genSequenceFromSampleIndices
from eventTimingGen import secsToTicks

from audio import genBeepSequence, saveAsWavFile
from video import genFlashSequence, genFrameImages

import re

# timings for how we will generate pulses depending on framerates
# each bit is represented by pulse(s). The first always occurs at the same
# moment. the second is only present if it is a one bit. For a zero bit, there
# is only one pulse.
#
# The timings are chosen depending on the frame rate so that they exactly align
# with frames. Timings are such that all times between flashes/beeps are
# unique depending on whether the bit is a zero or one ... not just between the
# two beeps/flashes conveying the bit, but also between the last beep/flash for
# the current bit and the first beep/flash for the next bit.

# values are +0.5 so that the centre of the pulse is in the middle of the frame's duration
fpsBitTimings = {
    25 : { 0 : [ 3.5/25  ],
           1 : [ 3.5/25, 9.5/25 ]
         },
    50 : { 0 : [ 3.5/25  ],
           1 : [ 3.5/25, 9.5/25 ]
         },
    30 : { 0 : [ 3.5/30 ],
           1 : [ 3.5/30, 9.5/30 ]
         },
    60 : { 0 : [ 3.5/30 ],
           1 : [ 3.5/30, 9.5/30 ]
         },
    24 : { 0 : [ 3.5/24 ],
           1 : [ 3.5/24, 9.5/24 ]
         },
    48 : { 0 : [ 3.5/24 ],
           1 : [ 3.5/24, 9.5/24 ]
         },
 }

# make durations of flashes and beeps long enough so that a skipped frame
# won't obliterate the flash/beep
flashNumDurationFrames = 3.0
idealBeepDurationFrames = 3.0


def genEventCentreTimes(seqBits, fps):
    """\
    Generator yields, in sequence, the times at which beeps/flashes should occur.

    It uses a maximal-length sequence (controlled by the number of its specified)
    to generate the list of timings of beep/flash pulses.

    The way the maximal-length sequence bitstream is mapped to timings of pulses
    depends on the frame-rate used. Only frame rates for which there are
    entries in fpsBitTimings are supported.

    :param seqBits: maximal-length sequence size in bits
    :param fps: Frame rate in frames per second.

    :returns: generator that yields a sequence of timings in units of seconds.
    """
    # decide what events (beeps or flashes) are going to be at what times
    # we generate a maximal length sequence (sequence of bits with no repeating patterns)
    bitStream = mls(bitLen=seqBits, limitRepeats=None)

    # now convert that to a set of timings of pulses (encoded with one pulse representing a zero bit
    # and two pulses representing a 1 bit)
    bitInterval = 1.0
    bitZeroTimings = fpsBitTimings[fps][0]
    bitOneTimings  = fpsBitTimings[fps][1]

    return encodeBitStreamAsPulseTimings(bitStream, bitInterval, bitZeroTimings, bitOneTimings)




def parseSizeArg(arg):
    match = re.match(r"^([1-9][0-9]*)x([1-9][0-9]*)$", arg)
    if not match:
        raise ValueError("Dimensions not provided in format WIDTHxHEIGHT, e.g. 854x480")
    else:
        return int(match.group(1)), int(match.group(2))


def parseSampleRate(arg):
    v = int(arg)
    if v<10000:
        raise ValueError("Sample rate must be at least 10kHz.")
    return v

def parseRGB(arg):
    match = re.match(r"^([0-9]+), *([0-9]+), *([0-9]+)$", arg)
    if not match:
        raise ValueError("Colour argument not in expected format R,G,B, e.g. 255,0,128 (note: no spaces between values)")
    else:
        r = int(match.group(1))
        g = int(match.group(2))
        b = int(match.group(3))
        if r<0 or r>255 or g<0 or g>255 or b<0 or b>255:
            raise ValueError("Colour values must be between 0 and 255 (inclusive)")
        else:
            return r,g,b

def parseSEGMENT(arg):
    match = re.match(r"^([^:]+):([0-9]+(?:\.[0-9]*)?):(.+)$", arg)
    if not match:
        raise ValueError("Segment argument not in expected format L:T:D where L = label text. T = Start time in seconds and fractions of a second. D - description text")
    else:
        return match.group(1), float(match.group(2)), match.group(3)

if __name__ == "__main__":

    import argparse
    import sys
    import os
    import json

    # defaults
    FPS         = 50
    WINDOW_LEN  = 7
    SIZE        = (854, 480)
    SAMPLE_RATE = 48000

    AUDIO_FILENAME = "build/audio.wav"
    FRAME_FILENAME_PATTERN = "build/img_%06d.png"
    METADATA_FILENAME = "build/metadata.json"

    parser=argparse.ArgumentParser(
        description="Generates a test sequence for timing measurement, consisting of a WAV file for the audio, and PNG image files for each frame, plus metadata describing the timings of flashes and beeps within the sequence.")

    parser.add_argument(
        "--fps", dest="FPS", action="store", nargs=1,
        type=int,
        choices=sorted(fpsBitTimings.keys()),
        default=[FPS],
        help="Frame rate measured in frames per second. Default is "+str(FPS))

    parser.add_argument(
        "--fields", dest="FIELD_BASED", action="store_true",
        default=False,
        help="If set, then twice as many frames will be output and each will be labelled as if they are fields (but will still be full vertical resolution). Default is Frame based")

    parser.add_argument(
        "--window-len", dest="WINDOW_LEN", action="store", nargs=1,
        type=int,
        choices=sorted(_mls_taps.keys()),
        default=[WINDOW_LEN],
        help="Unique pattern window length (in seconds). Beep/flash sequence will repeat after 2^n -1 seconds. Default is "+str(WINDOW_LEN)+" meaning the sequence repeats after "+str(2**WINDOW_LEN-1)+" seconds.")

    parser.add_argument(
        "--duration", dest="DURATION", action="store", nargs=1,
        type=int,
        default=[None],
        help="Duration of the sequence in seconds. Default is 2^n-1 where n is the \"pattern window length\".")

    parser.add_argument(
        "--size", dest="SIZE", action="store", nargs=1,
        type=parseSizeArg,
        default=[SIZE],
        help="WIDTHxHEIGHT dimensions in pixels of the video frame. Default is %dx%d" % SIZE)

    parser.add_argument(
        "--sampleRate", dest="SAMPLE_RATE", action="store", nargs=1,
        type=parseSampleRate,
        default=[SAMPLE_RATE],
        help="Audio sample rate in Hz. Minimum 10000 (10 kHz). Default is %d" % SAMPLE_RATE)

    parser.add_argument(
        "--frame-filename", dest="FRAME_FILENAME_PATTERN", action="store", nargs=1,
        type=str,
        default=[None],
        help="Filename pattern for writing PNG frames. Use printf style 'percent-d' syntax to include the frame number. Frames will not be written if this argument is provided")

    parser.add_argument(
        "--skip-frame-if-exists", dest="SKIP_IF_EXISTS", action="store_true",
        default=False,
        help="If set, then do not generate frame images if they already exist on the disk. Default is to generate all, even if they are already on the disk.")

    parser.add_argument(
        "--wav-filename", dest="AUDIO_FILENAME", action="store", nargs=1,
        type=str,
        default=[None],
        help="Filename for writing the WAV file. Audio will not be generated if this argument is not provided.")

    parser.add_argument(
        "--metadata-filename", dest="METADATA_FILENAME", action="store", nargs=1,
        type=str,
        default=[None],
        help="Filename for writing the JSON file containing metadata and beep/flash timings. Metadata will not be written if this argument is not provided")

    parser.add_argument(
        "--title", dest="TITLE_TEXT", action="store", nargs=1,
        type=str,
        default=[""],
        help="A title to be included in every video frame. Default=''")

    parser.add_argument(
        "--title-colour", dest="TITLE_COLOUR", action="store", nargs=1,
        type=parseRGB,
        default=[(255,255,255)],
        help="Colour for the title text as an R,G,B each between 0 and 255. Default=\"255,255,255\" (white)")

    parser.add_argument(
        "--bg-colour", dest="BG_COLOUR", action="store", nargs=1,
        type=parseRGB,
        default=[(0,0,0)],
        help="Colour for the background as R,G,B each between 0 and 255. Default=\"0,0,0\" (black)")

    parser.add_argument(
        "--text-colour", dest="TEXT_COLOUR", action="store", nargs=1,
        type=parseRGB,
        default=[(255,255,255)],
        help="Colour for the general text labels as an R,G,B each between 0 and 255. Default=\"255,255,255\" (white)")

    parser.add_argument(
        "--vi-colour", dest="GFX_COLOUR", action="store", nargs=1,
        type=parseRGB,
        default=[(255,255,255)],
        help="Colour for the visual indicator elements (moving blocks etc) as R,G,B each between 0 and 255. Default=\"255,255,255\" (white)")

    parser.add_argument(
        "--segments", dest="SEGMENTS", action="store", nargs="*",
        type=parseSEGMENT,
        default=[],
        help="List one or more segments on the time progress pie. Each argument should be <label>:<start_time_secs>:<description>"
    )

    args = parser.parse_args()

    fps = args.FPS[0]

    FIELD_BASED = args.FIELD_BASED
    if FIELD_BASED:
        # internally we render each "field" as a full "frame"
        fps=fps*2

    SKIP_IF_EXISTS = args.SKIP_IF_EXISTS

    seqBitLen = args.WINDOW_LEN[0]
    if args.DURATION[0] is None:
        sequenceDurationSecs = 2**seqBitLen - 1
    else:
        sequenceDurationSecs = args.DURATION[0]
    pixelsSize = args.SIZE[0]
    sampleRateHz = args.SAMPLE_RATE[0]
    frameFilenames = args.FRAME_FILENAME_PATTERN[0]
    audioFilename = args.AUDIO_FILENAME[0]
    metadataFilename = args.METADATA_FILENAME[0]
    title_text = args.TITLE_TEXT[0]
    title_colour = args.TITLE_COLOUR[0]
    bg_colour = args.BG_COLOUR[0]
    gfx_colour = args.GFX_COLOUR[0]
    text_colour = args.TEXT_COLOUR[0]

    if FIELD_BASED:
        frameLabel = "field"
    else:
        frameLabel = "frame"

    # check output directories exist
    for filename, purpose in [ (frameFilenames,   frameLabel+" images"),
                               (audioFilename,    "WAV file"),
                               (metadataFilename, "metadata JSON file") ]:
        if filename is not None and not os.path.isdir(os.path.abspath(os.path.dirname(filename))):
            sys.stderr.write("\nCould not find output directory for "+purpose+".\nPlease check it exists and create it if necessary.\n\n")
            sys.exit(1)

    print
    print "Generating sequence with following parameters:"
    print "   %s rate:                 %d fps" % (frameLabel.title(), fps)
    print "   Pattern window length:      %d seconds (meaning pattern will repeat every %d seconds)" % (seqBitLen, (2**seqBitLen-1))
    print "   Sequence duration:          %d seconds (%d frames)" % (sequenceDurationSecs, sequenceDurationSecs*fps)
    print "   Video frame dimensions:     %d x %d pixels" % pixelsSize
    print "   Audio sample rate:          %d Hz" % sampleRateHz
    print "   Filename for PNG frames:    %s " % (frameFilenames if frameFilenames is not None else "<< will not be saved >>")
    if frameFilenames is not None and SKIP_IF_EXISTS:
        print "                               (but will skip generating frames already on the disk)"
    print "   Filename for WAV audio:     %s " % (audioFilename if audioFilename is not None else "<< will not be saved >>")
    print "   Filename for JSON metadata: %s " % (metadataFilename if metadataFilename is not None else "<< will not be saved >>")
    print "   Text colour:                %d %d %d " % text_colour
    print "   Visual indicators colour:   %d %d %d " % gfx_colour
    print "   Background colour:          %d %d %d " % bg_colour
    if title_text != "":
        print "   Title:                      %s" % title_text
        print "   Title colour:               %d %d %d " % title_colour
    else:
        print "   No title."
    if args.SEGMENTS:
        print "    And with segments marked on the progress pie:"
        for i in range(0,len(args.SEGMENTS)):
            print "        Segment starting at t=%f secs" % args.SEGMENTS[i][1]
            print "            Pie label:   %s" % args.SEGMENTS[i][0]
            print "            Description: %s" % args.SEGMENTS[i][2]
    print ""

    # -----------------------------------------------------------------------

    # FIRST generate a WAV file containing audio with beeps of a fixed duration
    # with the centre of each beep corresponding to the time of the event

    toneHz = 3000
    amplitude = 32767*0.5
    idealBeepDurationSecs = idealBeepDurationFrames/fps

    if audioFilename is not None:
        # obtain a generator that can yield a never ending stream of beep timings
        eventCentreTimesSecs = genEventCentreTimes(seqBitLen, fps)

        # now we resolve that into an actual stream of sample data...

        # the genBeepSequence() generator converts the sequence of event times into
        # start and end times for the beep
        # corresponding to each event and also converts to audio sample data

        # the middle of each beep corresponding to the time of the event
        # choose beep duration carefully to match an exact number of cycles of the
        # tone sine wave to make it really nice and clean and symmetrical

        print "Generating audio..."
        seqIter = genBeepSequence(eventCentreTimesSecs, idealBeepDurationSecs, sequenceDurationSecs, sampleRateHz, toneHz, amplitude)

        print "Saving audio..."
        saveAsWavFile(seqIter, audioFilename, sampleRateHz)
    else:
        print "NOT generating audio (no filename provided)"

    # -----------------------------------------------------------------------

    # SECOND we'll do the video sequence

    idealFlashDurationSecs = flashNumDurationFrames/fps

    if frameFilenames is not None:
        black=(0,0,0)
        white=(255,255,255)

        # obtain a generator that can yield a never ending stream of flash timings
        eventCentreTimesSecs = genEventCentreTimes(seqBitLen, fps)

        # provide that as input to a new generator that yields a stream of
        # pixel colours for the flash for each frame. black=no flash. white=flash
        flashSequence = genFlashSequence(eventCentreTimesSecs, idealFlashDurationSecs, sequenceDurationSecs, fps, black, white)

        # do a second version for the pip train using the gfx and bg colors
        eventCentreTimesSecs = genEventCentreTimes(seqBitLen, fps)
        pipTrainSequence = genFlashSequence(eventCentreTimesSecs, idealFlashDurationSecs, sequenceDurationSecs, fps, bg_colour, gfx_colour)

        flashSequence = list(flashSequence) # flatten so we can know the length
        frameNum=0

        print "Generating video images..."
        numNumberSubstitutions = len(re.findall(r"%.?[0-9]*d", frameFilenames))

        def genFrameFilename(n):
            return frameFilenames % tuple([n] * numNumberSubstitutions)

        if SKIP_IF_EXISTS:
            skipChecker = lambda n : os.path.isfile(genFrameFilename(n))
        else:
            skipChecker = None

        # pass the flash sequence pixel colour generator to a new generator that
        # will yield a sequence of image frames
        
        segments = map(lambda (label,startSecs,description) : {
            "startSecs": startSecs,
            "label": label,
            "description": label+": "+description
        }, args.SEGMENTS)

        numFrames = len(flashSequence)
        frames = genFrameImages(pixelsSize, flashSequence, pipTrainSequence, numFrames, fps, \
            BG_COLOUR=bg_colour, GFX_COLOUR=gfx_colour, TEXT_COLOUR=text_colour, title=title_text, TITLE_COLOUR=title_colour, \
            FRAMES_AS_FIELDS=FIELD_BASED, frameSkipChecker=skipChecker, segments=segments )
        n=0
        for frame in frames:
            filename = genFrameFilename(n)
            if frame is not None:
                print "    Generating and saving image %d of %d" % (n, numFrames-1)
                frame.save(filename, format="PNG")
            else:
                print "    Skipping image %d of %d (already exists)" % (n, numFrames-1)
            n=n+1
    else:
        print "NOT generating video images (no filename provided)"

    # -----------------------------------------------------------------------

    # THIRD we'll write out metadata

    if metadataFilename is not None:
        print "Generating and writing metadata..."

        # obtain a generator that can yield a never ending stream of flash timings
        eventCentreTimesSecs = genEventCentreTimes(seqBitLen, fps)

        timings = []
        for eventTime in eventCentreTimesSecs:

            # check if we've reached the end, and exit the loop if we have
            if eventTime >= sequenceDurationSecs:
                break
            else:
                timings.append(eventTime)



        # assemble the metadata into a structure and write out as JSON file
        metadata = {
            "size" : [ pixelsSize[0], pixelsSize[1] ],
            "fps" : fps,
            "durationSecs" : sequenceDurationSecs,
            "patternWindowLength" : seqBitLen,
            "eventCentreTimes" : timings,
            "approxBeepDurationSecs" : idealBeepDurationSecs,
            "approxFlashDurationSecs" : idealFlashDurationSecs,
        }

        jsonString = json.dumps(metadata)
        f=open(metadataFilename, "wb")
        f.write(jsonString)
        f.close()
    else:
        print "NOT generating metadata file (no filename provided)"

    print "Done."
    print
