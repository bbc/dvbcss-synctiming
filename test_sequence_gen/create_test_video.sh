#!/bin/sh
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


# --------------------------------------------------------------------------
# this script shows how to run the sequence generator and then encode the
# resulting audio and video frame images into MP4, MPEG TS and MPEG PS files

# Temporary image files are put into a directory whose name begins "build-tmp"
# the metadata describing flash/beep timings and the video files are put
# into the current directory

# tested with ffmpeg 2.5.1
#
# known to NOT work with avconv from ubuntu 14.04

FFMPEG=`which ffmpeg avconv | head`
if [ -z "$FFMPEG" ]; then
	echo "Need to have ffmpeg or avconv installed and in the path to run." >&2
	exit 1
fi

# --------------------------------------------------------------------------
# parameters

FPS=50
WINDOW_LEN=7
SIZE=854x480

## alternative parameters for a quick-to-create video
#FPS=25
#WINDOW_LEN=3
#SIZE=320x180


# --------------------------------------------------------------------------
# define file and directory names based on parameters

NAME_FRAGMENT="$FPS"fps_"$WINDOW_LEN"bitseq_"$SIZE"pixels

TMPDIR="build/tmp.""$NAME_FRAGMENT"

OUTDIR="build"

METADATA_FILE="$OUTDIR""/metadata.""$NAME_FRAGMENT"".json"
VIDEO_FILE="$OUTDIR""/video.""$NAME_FRAGMENT"

FRAME_FILE_PATTERN="$TMPDIR"/"img_%09d.png"
WAV_FILE="$TMPDIR"/"audio.wav"

# --------------------------------------------------------------------------
# create directories for temp files

mkdir -p "$TMPDIR"
mkdir -p "$OUTDIR"

rm -f "$TMPDIR"/*.png
rm -r "$TMPDIR"/*.wav


# --------------------------------------------------------------------------
# run the sequence generator

./src/generate.py \
	--fps "$FPS" --size "$SIZE" --window-len "$WINDOW_LEN" \
	--frame-filename    "$FRAME_FILE_PATTERN" \
	--wav-filename      "$WAV_FILE" \
	--metadata-filename "$METADATA_FILE" \

if [ $? -ne 0 ]; then
	echo "Error during creation of wav/png/metadata. Aborting" >&2
	exit 2
fi

# --------------------------------------------------------------------------
# encode using ffmpeg

# MP4 using H264 and AAC audio

$FFMPEG -y \
 	-r "$FPS" -i "$FRAME_FILE_PATTERN" -f wav -i "$WAV_FILE" \
 	-b 2M -r "$FPS" -vcodec libx264 -vf "fps=$FPS,format=yuv420p" \
 	-preset:v slow -profile:v baseline -level 3.1 -crf 23 \
 	-ac 2 -ar 48k -ab 128k -acodec aac -strict -2 \
 	-map 0:v:0 -map 1:a:0 \
 	"$VIDEO_FILE".mp4

if [ $? -ne 0 ]; then
	echo "Failure when creating MP4. Aborting" >&2
	exit 3
fi


# MPEG TRANSPORT STREAM and MPEG PROGRAM STREAM
# ... using MPEG2 video and mp2 audio

# we carefully control the PTS value of the first frame.
# note that FFMPEG needs it to be greater than zero because the decode timestamp
# is a smaller value and FFMPEG cannot cope with the idea of a negative DTS (!)

START_PTS_IN_SECONDS=10.0  # PTS will be this * 90000

PTS_TB=1/90000
VPTS_FUNC="N/(TB*FRAME_RATE) + ""$START_PTS_IN_SECONDS""/TB"
APTS_FUNC="N/(TB*SAMPLE_RATE) + ""$START_PTS_IN_SECONDS""/TB"


$FFMPEG -y \
	-r "$FPS" -i "$FRAME_FILE_PATTERN" -f wav -i "$WAV_FILE" \
	-b 2M -r "$FPS" -vcodec mpeg2video -vf settb="$PTS_TB" -vf setpts="$VPTS_FUNC" \
	-ac 2 -ar 48k -ab 128k -acodec mp2 -af asettb="$PTS_TB" -af asetpts="$APTS_FUNC" \
	-map 0:v:0 -map 1:a:0 \
	-mpegts_copyts 1 \
	"$VIDEO_FILE".ts

if [ $? -ne 0 ]; then
	echo "Failure when creating MPEG TS. Aborting" >&2
	exit 4
fi


$FFMPEG -y \
	-r "$FPS" -i "$FRAME_FILE_PATTERN" -f wav -i "$WAV_FILE" \
	-b 2M -r "$FPS" -vcodec mpeg2video -vf settb="$PTS_TB" -vf setpts="$VPTS_FUNC" \
	-ac 2 -ar 48k -ab 128k -acodec mp2 -af asettb="$PTS_TB" -af asetpts="$APTS_FUNC" \
	-map 0:v:0 -map 1:a:0 \
		"$VIDEO_FILE".mpg

if [ $? -ne 0 ]; then
	echo "Failure when creating MPEG PS. Aborting" >&2
	exit 5
fi

echo ""
echo "--------------------------------------------------------------------------"
echo ""
echo "Completed successfully!"
echo ""
echo "    Intermediate image and audio files in: $TMPDIR/"
echo "    Video files:"
echo "        $VIDEO_FILE.mp4"
echo "        $VIDEO_FILE.ts"
echo "        $VIDEO_FILE.mpg"
echo "    Metadata file:"
echo "        $METADATA_FILE"
echo ""
echo "--------------------------------------------------------------------------"
echo ""
