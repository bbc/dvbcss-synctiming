# Synchronisation timing video test sequence generator

The scripts in this directory will generate a still image sequence and
corresponding WAV file that can be converted into a video file containing a
sequence of aligned and carefully timed "beeps" and "flashes".

This can be used for checking alignment between audio and video, and also for
checking synchronisation timing when the video is being played by a device
using the [DVB companion screen synchronisation
protocols](https://www.github.com/BBC/pydvbcss) ... by comparing the times at
which flashes and beeps occur to the times at which they should have occurred
given the messages flowing via the CSS-TS protocol describing the timing of
video playback.



## Getting started


### 1. Install dependencies

Make sure you have **ffmpeg** and **PIL** (the Python Image Library)
installed and a [Python](http://www.python.org) interpreter and bash shell.
The latest version of PIL is known as "pillow".

*On Mac OS X and Linux you may need to run one or more of the commands as root.*

We recommend using [pip](https://pip.pypa.io/en/latest/installing.html) to install
python libraries from the Python Package Index [PyPI](https://pypi.python.org/pypi):

	$ pip install pillow

*Note: This now requires pillow **version 3.4 or later**. Add the `-U` option when
running `pip install` to force an upgrade if you have an earlier version installed.*

**ffmpeg** should be installed using your system's package manager or
[downloaded direct](https://www.ffmpeg.org/)  as
appropriate. On Debian systems (e.g. Ubuntu):

	$ apt-get install ffmpeg

*Note: avconv (an ffmpeg alternative) as supplied with Ubuntu 14.04 is not
suitable. However the builds you can [obtain direct from ffmpeg's
website](https://www.ffmpeg.org/) do work.*

And on Mac Ports for Mac OS X:

	$ port install ffmpeg


### 2. Run the example script to build a test sequence video
	
The shell script ``create_test_video.sh`` will generate a reasonable length
sequence at standard definition resolution and encode it in a few file
formats. Just run it:

	$ ./create_test_video.sh


### 3. Look at the generated video and metadata

The temporary intermediate files and the resulting video files are all put
into a `build` sub-directory that is created.

A metadata file in JSON format is also placed into the `build` directory.
This contains the precise timings of the mid point of each beep and flash as
a number of seconds since the beginning of the video.

For example:

    {
        "eventCentreTimes": [
        	0.14, 0.52, 1.14, 1.38, 2.14, 2.52, 3.14,
        	3.52, 4.14, 4.52, 5.14, 5.38, 6.14, 6.38
        ],
        "durationSecs": 7,
        "patternWindowLength": 3,
        "fps": 25,
        "size": [320, 180],
        "approxFlashDurationSecs": 0.12,
        "approxBeepDurationSecs": 0.12
    }

The list of timings is essential input to any process that wishes to check
whether a companion screen is correctly synchronised to Control Timestamps it
receives; or a TV Device is sending out Control Timestamps that accurately
match what it is actually doing.

The information on the approximate durations of the flashes and beeps is used to tune the flash/beep detection algorithms.

The formats outputted are:

 * MP4 (.mp4) containing H.264 video and AAC audio
 * MPEG PS (.mpg) and MPEG TS (.ts) containing mpeg2 video and MP2 audio, with
   the first frame's PTS value being 900000.
   

## Customising the parameters used to generate the video
	
You can generate other duration, resolution, framerate etc sequences by
customising `create_test_video.sh`.

The main code that generates the individual image files and the audio track is
``generate.py``. Run this with the ``--help`` option to see a full list of
command line options.


## Why do the beeps/flashes happen in an irregular pattern?

The pattern of timings of each beep and flash is arranged such that if you observe a short
chunk of the video (of a certain minimum duration) then you will never see that
pattern repeat.

The timings are derived from a [maximal-length sequence](http://en.wikipedia.org/wiki/Maximum_length_sequence)
generated using parameters found [here](http://en.wikipedia.org/wiki/Linear_feedback_shift_register#Some_polynomials_for_maximal_LFSRs).
This can be thought of as a stream of bits (zeros and ones).

During each 1 second interval, there is either 1 or 2 beeps/flashes,
denoting a zero or a one respectively from the maximal-length sequence. The
timings are chosen to align exactly with frames. Where a pair of
beeps/flashes are used, they are timed close together to make it easy to
distinguish which is the first in the pair and which is the second.

An N-bit maximal-length sequence is a sequence of 2^N-1 bits in length. It
has the property that any N-bit long sub-sequence will occur only once within
the sequence.

For example: a 5 bit sequence results in a sequence of beeps/flashes that is
31 seconds long (2^5-1) where if you observe any 5 second (or longer) period
you will not see the same pattern of flashes/beeps anywhere else in the
sequence.

This is obviously a very useful property when trying to measure how a set of
observations of the timings of flashes/beeps aligns.

A sequence that repeats regularly (e.g. a flash/beep every 1 second) could be
aligned in many different ways, all indistinguishable.

The use of different numbers of beeps/flashes to denote a zero or one bit in
the pattern makes it easier for algorithms to spot which part of the sequence
the observed beeps/flashes match up to.

