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

import itertools
import math
import struct
import sys

from eventTimingGen import calcNearestDurationForExactNumberOfCycles
from eventTimingGen import genSequenceStartEnds
from eventTimingGen import secsToTicks
from eventTimingGen import genSequenceFromSampleIndices

try:
    from PIL import Image
    from PIL import ImageDraw
    from PIL import ImageFont
except ImportError:
    print >> sys.stderr, "\n".join([
        "",
        "Error importing PIL (Python Image Library). Is it installed? Suggest installing using PIP, e.g.:",
        "",
        "    sudo pip install pillow\n",
        ""
        ])
    sys.exit(1)



def genFlashSequence(flashCentreTimesSecs, idealFlashDurationSecs, sequenceDurationSecs, frameRate, gapValue=(0,0,0), flashValue=(1.0,1.0,1.0)):
    """\
    Generates the pixel colour values needed for each frame to render flashes corresponding to the timings specified.

    :param beepCentreTimeSecs: A list or iterable of the centre times of each beep (in seconds since the beginning of the sequence)
    :param idealFlashDurationSecs: ideal duration of a flash in seconds
    :param sequenceDurationSecs: total sequence duration in seconds
    :param sampleRateHz: The final output sample rate in Hz
    :param gapValue: The value for non flash pixels
    :param flashValue: The value for flash pixels

    :returns: An iterable that generates the pixel colours for each frame starting with the first frame
    """
    flashDurationSamples = calcNearestDurationForExactNumberOfCycles(idealFlashDurationSecs, frameRate)

    flashStartEndSamples = genSequenceStartEnds(flashCentreTimesSecs, flashDurationSamples, 1.0, frameRate)

    nSamples = sequenceDurationSecs * frameRate

    def gapGen():
        while True:
            yield gapValue

    def flashGen():
        while True:
            yield flashValue

    seqIter = genSequenceFromSampleIndices(flashStartEndSamples, gapGen, flashGen)

    return itertools.islice(seqIter, 0, nSamples)





def secsToFrames(tSecs, startFrame, fps):
    return secsToTicks(tSecs, startFrame, fps)






class AspectPreservingCoordinateScaler(object):
    """\
    Converts coordinates from a bounding box (0,0) -> (inputWidth, inputHeight)
    to coordinates within another bounding box (0,0) -> (outputWidth, outputHeight)

    Does so such that the aspect ratio is preserved and such that the input
    bounding box would be centred within the output bounding box.
    """

    def __init__(self, (inputWidth, inputHeight), (outputWidth, outputHeight)):
        super(AspectPreservingCoordinateScaler,self).__init__()

        # work out how much we need to shrink/enlarge input coordinates to make
        # then fit within the output coordinates entirely, if we preserve the
        # aspect ratio

        widthScale = float(outputWidth) / inputWidth
        heightScale = float(outputHeight) / inputHeight

        self.scale = min(widthScale, heightScale)

        xGap = outputWidth - inputWidth*self.scale
        yGap = outputHeight - inputHeight*self.scale

        self.xOffset = xGap / 2.0
        self.yOffset = yGap / 2.0

    def xy(self, (x,y)):
        """Translate (x,y) coordinate"""
        x = x * self.scale + self.xOffset
        y = y * self.scale + self.yOffset
        return (int(x),int(y))

    def s(self, v):
        return v * self.scale

def loadFont(sizePt):
    possibleFonts = [ "Arial.ttf", "arial.ttf", "FreeSans.ttf", "freesans.ttf" ]

    for fontName in possibleFonts:
        try:
            return ImageFont.truetype(fontName, int(sizePt))
        except IOError:
            pass

    possibleFontFiles = [
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/FreeSans.ttf",
    ]

    for fontFile in possibleFontFiles:
        try:
            return ImageFont.truetype(filename=fontFile, size=int(sizePt))
        except IOError:
            pass
    raise RuntimeError("Cannot find a TTF font file.")


FIELD_INDICATOR = [
    unichr(0x25cb)+u"1",     # hollow circle, '1'
    unichr(0x25cf)+u"2",     # filled circle, '2'
]

def frameNumToTimecode(n, fps, framesAreFields=False):
    f = n % fps
    s = (n / fps) % 60
    m = (n / fps / 60) % 60
    h = (n / fps / 60 / 60)

    if framesAreFields:
        fieldIndicator = u'  ' + FIELD_INDICATOR[f % 2]
        f = f / 2
    else:
        fieldIndicator = ""

    return "%02d:%02d:%02d:%02d%s" % (h,m,s,f, fieldIndicator)


def precise_filled_pieslice(draw, xy, start, end, *options, **kwoptions):
    """\
    Enhanced version of pieslice drawing code that copes with fractional
    angles.
    """
    startInt = int(math.ceil(start))
    endInt   = int(math.floor(end))

    draw.pieslice(xy, startInt, endInt, *options, **kwoptions)

    # draw triangular wedges for the final fraction of degree at the start and end

    if len(xy) == 2:
        x1,y1 = xy[0]
        x2,y2 = xy[1]
    elif len(xy) == 4:
        x1,y1 = xy[0], xy[1]
        x2,y2 = xy[2], xy[3]
    else:
        raise ValueError("Did not know how to interpret xy value list")

    centre = (x1+x2)/2.0, (y1+y2)/2.0
    xrad = abs((x2-x1)/2.0)
    yrad = abs((y2-y1)/2.0)

    if start != startInt:
        p1 = centre[0] + xrad * math.cos(math.radians(start)), \
             centre[1] + xrad * math.sin(math.radians(start))
        p2 = centre[0] + xrad * math.cos(math.radians(startInt)), \
             centre[1] + xrad * math.sin(math.radians(startInt))
        draw.polygon([centre, p1, p2, centre], *options, **kwoptions)

    if end != endInt:
        p1 = centre[0] + xrad * math.cos(math.radians(end)), \
             centre[1] + xrad * math.sin(math.radians(end))
        p2 = centre[0] + xrad * math.cos(math.radians(endInt)), \
             centre[1] + xrad * math.sin(math.radians(endInt))
        draw.polygon([centre, p1, p2, centre], *options, **kwoptions)


def genFrameImages((widthPixels, heightPixels), flashColourGen, flashColourGenPipTrain, numFrames, FPS, superSamplingScale=8, BG_COLOUR=(0,0,0), TEXT_COLOUR=(255,255,255), GFX_COLOUR=(255,255,255), title="", TITLE_COLOUR=(255,255,255), FRAMES_AS_FIELDS=False, frameSkipChecker=None, segments=[]):
    """\
    Generator that yields PIL Image objects representing video frames, one at a time

    :param (widthPixels, heightPixels): desired dimensions (in pixels) of the image as a tuple
    :param flashColourGen: a list or iterable (e.g. generator) that returns the colour to use for the flashing box
    :param flashCOlourGen: a list or iterable (e.g. generator) that returns the colour to use for the pip train
    :param numFrames: the number of frames to create
    :param FPS: the frame rate
    :param superSamplingScale: Scale factor used to achieve anti-aliasing. e.g. 8 means the image will be drawn x8 too large then scaled down by a factor of 8 to smooth it before it is yielded
    :param BG_COLOUR: background colour as (r,g,b) tuple
    :param TEXT_COLOUR: text label colour as (r,g,b) tuple
    :param GFX_COLOUR: colour for graphical indicators (except the pips) as (r,g,b) tuple
    :param title: title text label
    :param TITLE_COLOUR: colour for the title text as (r,g,b) tuple
    :param FRAMES_AS_FIELDS: false if frames will be used as frames. True if outputted frames will be encoded as fields.
    :param frameSkipChecker: None or a function that takes the frame number as input and returns True if the frame should not be generated (in which case None will be yielded in place of a frame image)
    :param segments: Array of dict structures describing segments with labels and descriptions. Each entry has following key/value pairs: "label":string label shown on the pie. "startSecs":number of seconds (including fractions) at which segment begins. "description":string - descriptive string given for the segment
    :returns: Generator that yields a PIL.Image object for every frame in sequence
    """

    # we're going to draw a larger (super sampled) image and then scale it down
    # to get smoothing (compensating for the lack of anti-aliased drawing functions
    # in PIL)

    width = widthPixels * superSamplingScale
    height = heightPixels * superSamplingScale

    flashCols = list(flashColourGen)[0:numFrames]
    flashColsPipTrain = list(flashColourGenPipTrain)[0:numFrames]

    # we'll pretend we're working within a rectangle (0,0) - (160,90)
    # and use a scaling function to map to out actual dimensions
    scaler = AspectPreservingCoordinateScaler((160,90),(width,height))

    # load a font for text
    font = loadFont(sizePt = scaler.s(4))
    smallfont = loadFont(sizePt = scaler.s(4))
    
    # work out the segment description text, then check its size and adjust the fontsize to ensure it fits within bounding area
    if segments:
        segment_description_text = "\n".join(map(lambda seg : seg["description"], segments))
        tmpimg = Image.new("RGB", (width, height), color=BG_COLOUR)
        tmpdraw = ImageDraw.Draw(tmpimg)
        w,h = tmpdraw.multiline_textsize(segment_description_text, font=smallfont)
        max_w, max_h = scaler.xy((140,13))
        
        shrink_factor = min(float(max_w) / w, float(max_h) / h, 1)
        smallfont = loadFont(sizePt = scaler.s(4*shrink_factor))
    
    poy = 0 # pie Y offset
    dfy = 65 # duration and FPS labels Y offset
    if segments:
        poy = -10
        dfy = 19



    WHITE=(255,255,255)
    BLACK=(0,0,0)

    if FRAMES_AS_FIELDS:
        imageName = "field"
        labelFps = FPS / 2
    else:
        imageName = "frame"
        labelFps = FPS


    for frameNum in range(0,numFrames):
        if frameSkipChecker is not None:
            shouldSkip=frameSkipChecker(frameNum)
            if shouldSkip:
                yield None
                continue

        timecode = frameNumToTimecode(frameNum, FPS, framesAreFields=FRAMES_AS_FIELDS)
        timeSecs = float(frameNum) / FPS
        nextTimeSecs = float(frameNum+1) / FPS  # time of next frame after this
        durationTimecode = frameNumToTimecode(numFrames, FPS)

        # create black image and an object to let us draw on it
        img = Image.new("RGB", (width, height), color=BG_COLOUR)
        draw = ImageDraw.Draw(img)

        # draw a flashing rectangular box on the left side
        flashColour = flashCols[frameNum]
        topLeft     = scaler.xy((10, 30))
        bottomRight = scaler.xy((40, 60))
        draw.rectangle(topLeft + bottomRight, outline=None, fill=GFX_COLOUR)
        topLeft     = scaler.xy((11, 31))
        bottomRight = scaler.xy((39, 59))
        draw.rectangle(topLeft + bottomRight, outline=None, fill=flashColour)

        # draw text label explaining to attach light sensor to the flashing box
        topLeft     = scaler.xy((41, 37))
        draw.text(topLeft, "Use light detector", font=font, fill=TEXT_COLOUR)
        topLeft     = scaler.xy((41, 41))
        draw.text(topLeft, "on centre of", font=font, fill=TEXT_COLOUR)
        topLeft     = scaler.xy((41, 45))
        draw.text(topLeft, "this box", font=font, fill=TEXT_COLOUR)

        # draw text labels giving frame number, timecode and seconds covered by this frame
        topLeft = scaler.xy((10, 4))
        draw.text(topLeft, timecode, font=font, fill=TEXT_COLOUR)
        topLeft = scaler.xy((10, 9))
        draw.text(topLeft, "%06d of %d %ss" % (frameNum, numFrames, imageName), font=font, fill=TEXT_COLOUR)
        topLeft = scaler.xy((10, 14))
        draw.text(topLeft, u"%08.3f \u2264 t < %08.3f secs" % (timeSecs, nextTimeSecs), font=font, fill=TEXT_COLOUR)

        topLeft = scaler.xy((10,dfy))
        draw.text(topLeft, "Duration: " + durationTimecode, font=font, fill=TEXT_COLOUR)
        topLeft = scaler.xy((10,dfy+5))
        draw.text(topLeft, "%d fps" % labelFps, font=font, fill=TEXT_COLOUR)

        # and more text labels, but this time right justified
        text = title
        w,h = font.getsize(text)
        topLeft = scaler.xy((150,4))
        topLeft = topLeft[0] - w, topLeft[1]
        draw.text(topLeft, text, font=font, fill=TITLE_COLOUR)

        # draw an outer ring segment indicating the time period covered by the current frame
        topLeft = scaler.xy((105, 20+poy))
        bottomRight = scaler.xy((155, 70+poy))
        angle1 = 360 * (frameNum % FPS) / FPS
        angle2 = 360 * ((frameNum % FPS) + 1) / FPS
        draw.pieslice(topLeft + bottomRight, start=270+angle1, end=270+angle2, outline=None, fill=GFX_COLOUR)

        # hollow it out to make the circle into a ring
        topLeft = scaler.xy((108, 23+poy))
        bottomRight = scaler.xy((152, 67+poy))
        draw.ellipse(topLeft + bottomRight, outline=None, fill=BG_COLOUR)


        # draw frame num ring
        topLeft = scaler.xy((110, 25+poy))
        bottomRight = scaler.xy((150, 65+poy))
        angle = 360 * (frameNum % FPS) / FPS
        if (frameNum / FPS) % 2 == 0:  # if this is an even second (0-0.9, 2-2.9, 4-4.9 etc)
            draw.pieslice(topLeft + bottomRight, start=270, end=270+angle, outline=None, fill=GFX_COLOUR)
        else:
            draw.pieslice(topLeft + bottomRight, start=270+angle, end=270+360, outline=None, fill=GFX_COLOUR)

        # hollow it out to make the circle into a ring
        topLeft = scaler.xy((113, 28+poy))
        bottomRight = scaler.xy((147, 62+poy))
        draw.ellipse(topLeft + bottomRight, outline=None, fill=BG_COLOUR)
        
        # draw outer for segments
        if segments:
            topLeft = scaler.xy((115-0.25, 30+poy-0.25))
            bottomRight = scaler.xy((145+0.25, 60+poy+0.25))
            draw.ellipse(topLeft + bottomRight, fill=WHITE, outline=None)
            topLeft = scaler.xy((115, 30+poy))
            bottomRight = scaler.xy((145, 60+poy))
            draw.ellipse(topLeft + bottomRight, fill=BLACK, outline=None)

        # draw progress pie
        topLeft = scaler.xy((115, 30+poy))
        bottomRight = scaler.xy((145, 60+poy))
        angle = 360.0*frameNum/numFrames
        precise_filled_pieslice(draw, topLeft + bottomRight, start=270, end=270+angle, outline=None, fill=GFX_COLOUR)

        # draw segments over the pieslice
        if segments:
            for i in range(0, len(segments)):
                angle = math.radians(270 + 360.0*segments[i]["startSecs"]/numFrames*FPS)
                centre = scaler.xy((130,45+poy))
                armEnd = scaler.xy((130 + 15*math.cos(angle), 45+poy + 15*math.sin(angle)))
                draw.line([centre, armEnd], fill=WHITE, width=int(scaler.s(0.25)))
                
                segStartFrame = segments[i]["startSecs"] * FPS
                nextStartFrame = segments[(i+1) % len(segments)]["startSecs"] * FPS
                if nextStartFrame <= segStartFrame:
                    nextStartFrame += numFrames
                midAngle = math.radians(270 + 360.0* (segStartFrame+nextStartFrame)/2/numFrames)
                w,h = font.getsize(segments[i]["label"])
                centre = scaler.xy((130 + 15*math.cos(midAngle)*0.7, 45+poy + 15*math.sin(midAngle)*0.7))
                topLeft = centre[0] - w/2, centre[1] - h/2
                draw.text(topLeft, segments[i]["label"], fill=WHITE, font=font)

            # draw segment long labels
            topLeft = scaler.xy((10,61))
            draw.multiline_text(topLeft, segment_description_text, fill=WHITE, font=smallfont)
        
        # draw pulse train at the bottom
        LIM=FPS
        NUM_BLOBS = 2*LIM + 1
        blobSpacing = 150.0/NUM_BLOBS

        for offset in range(-LIM, +LIM+1):
            left  = 80+blobSpacing*(offset-0.5)
            right = 80+blobSpacing*(offset+0.5)

            topLeft     = scaler.xy(( left, 80 ))
            bottomRight = scaler.xy(( right, 85 ))

            seqIndex = offset + frameNum
            if seqIndex >= 0 and seqIndex < numFrames:
                colour = flashColsPipTrain[seqIndex]
                draw.rectangle(topLeft + bottomRight, outline=None, fill = colour)

            if offset == 0:
                # draw blob above
                topLeft     = scaler.xy(( left, 75 ))
                bottomRight = scaler.xy(( right, 80 ))
                draw.rectangle(topLeft + bottomRight, outline=None, fill = GFX_COLOUR)

                # and below
                topLeft     = scaler.xy(( left, 85 ))
                bottomRight = scaler.xy(( right, 90 ))
                draw.rectangle(topLeft + bottomRight, outline=None, fill = GFX_COLOUR)

        # shrink the image using high quality downsampling
        try:
            scalingMode = Image.LANCZOS
        except AttributeError:
            scalingMode = Image.BICUBIC

        rescaledImage = img.resize((widthPixels,heightPixels), scalingMode)

        yield rescaledImage
