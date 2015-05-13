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


r"""
This module provides functions to analyses the timings of the detected
beep/flashes and compare them against expected timings of beep/flashes to
determine which observed ones correspond to which expected ones.

So for any given light sensor or audio input we have a set of observed timings
of beeps/flashes and a set of expected timings of beeps/flashes. The observed
are subset range of the expected.

"expected" describes N events for the entire video clip.  "observed" describes M events observed
during synchronised playback of some portion of the video.  M <= N.

The analysis runs a correlation using "expected" and "observed".  The problem we're solving
is which portion of the events in "expected" correlates the strongest with the events
in "observed".  To do this we slide the set of events in "observed" along the set of events
in "expected".  We start at event 0 in "expected" and compare M events with "observed".
Then we do the same starting at event 1 in "expected" and compare M events with "observed".
The last index we can use to extract M events in "expected" is N - M.

For a given set of M events from expected, we then build a set of time differences, one entry
per event. We calculate the variance for the data in this set of differences, and remember this
as an indicator of "goodness of match", along with the start index involved.

Once we have done this at all possible start points along "expected", we then have N-M variances.
The one with the lowest value is the best match.

If the master and client were perfectly synchronised, then we'd have a time difference set
of all zero's and the variance would be zero.  A realistic situation would show the time
differences (mostly) clustering around constant value, but the variance will still be low.

That is, plotting on a graph with synchronisation timeline values on the x-axis, and
time difference values on the y-axis, then the average offset is a horizontal line
and the variance quantifies how much the data differs from this ideal. A high variance
indicates that the pattern of observed beep/flash timings did not match that
particular subset of the expected beep/flash timings.

If the pattern for the time differences is sloping, this indicates wall clock drift.

"""



def variance(dataset):
    """\
    Given a set of time differences, compute the variance in this set
    :param dataset: list of values
    :returns: the variance
    """
    avg = sum(dataset)/len(dataset)
    v = 0.0
    for data in dataset:
        v += (data - avg) * (data - avg)
    v = v / len(dataset)
    return v



def varianceInTimesWithObservedComparedAgainstExpectedAtIndex(idx, expected, observed):
    """\
    Traverse the list of expected times, starting from index "idx", and the list of observed
    times, starting from index 0, for the full length of the observed times list, to generate
    a list of the time difference between each expected time and observed time.  Then compute the
    variance in the time difference, and return it, along with the differences from which it
    was calculated.
    
    :param idx: index into expected times at which start traversal
    :param expected: list of expected times in units of sync time line clock
    :param observed: list of tuples of (detected centre flash/pulse time, err bounds), in units of sync time line clock
   
    :returns: tuple (variance, differencesAndErrors)
     * variance = statistical variance of the difference between expected and observed timings    
     * differencesAndErrors is a list, of (diff,err) representing each time difference and the error bound for the respective measurement
     
    """
    where = idx
    differences = []
    differencesAndErrors = []
    for e in observed:
        # e[0] is the observed time.  e[1] is the error bound
        diff = expected[where] - e[0]
        differences.append( diff )
        differencesAndErrors.append( (diff, e[1]) )
        where += 1
    return (variance(differences), differencesAndErrors)


def correlate(expected, observed):
    """\
    
    Perform a correlation between a list of expected timings, and a list of
    observed timings that ought to "match" against some contiguous portion
    of the expected timings.
    
    We work out the last possible index into the expected timings so that traversal from
    there to the end of its list has the same number of entries as in the observed timings list.
    
    Starting at index 0 of the expected list, we then compute the variance in time differences
    between each expected time and an observed time (running from index 0 of the observed timings).
    
    We repeat this from index 1 .. last possible index, each time computing the variance
    in time differences between each expected time and an observed time (running from index 0 of the observed timings)
    
    For each of the runs, we add a tuple of (expected time index, variance computed) to a list.
    
    Finally, we then traverse this list, looking for the lowest variance value.  This is the point in the
    expected times that most closely matches the observed timings.
    
    :param expected: list of expected times in units of sync time line clock
    :param observed: list of tuples of (detected centre flash/pulse time, err bounds), in units of sync time line clock

    :returns (index, timeDifferences): A tuple containing the index in the expected
        timings corresponding to the first observation, and a list of the time differences between each individual
        observed and expected flash/beep for the match.
        
        if there are more detected flashes/beeps than expected, it is probably due to a wrong input
        being plugged into on the Arduino, compared to what was asked for via the command line.  In this case
        we return a tuple (-1, None)
            
    """
    # following list will hold all sets of time differences computed during the correlation.
    # entry j will hold the set found when observed was compared with expected starting at j.
    timeDifferencesAndErrorsAtIndices = []
    
    # the observed timings will be a subset of the expected times
    # so figure out the last start index in the observed timings
    # that accommodates the length of these observed timings
    lastPossible = len(expected) - len(observed)

    varianceAtEachIndex = []
    
    # now look for the set of observed timings against each
    # possible starting point.  Each loop traversal, observed[0] will be compared against
    # expected[where]. observed[1] against expected[where+1]
    for where in range(0, lastPossible + 1):
        variance, diffsAndErrors = varianceInTimesWithObservedComparedAgainstExpectedAtIndex(where, expected, observed)
        timeDifferencesAndErrorsAtIndices.append(diffsAndErrors)
        varianceAtEachIndex.append((variance, where))
        
    (lowestVariance, index) = min(varianceAtEachIndex)
    return (index, timeDifferencesAndErrorsAtIndices)




def doComparison(test, startSyncTime, tickRate):
 
    """\
    Each activated pin results in a test set: the observed and expected times.
    For each of these tests, perform the comparison.
    
    :param A tuple is a
        ( list of tuples of (observed times (sync time line units), error bounds), list of expected timings (seconds) )
    :param startSyncTime: the start value used for the sync time line offered to the client device
    :param tickRate: the number of ticks per second for the sync time line offered to the client device

    :returns tuple summary of results of analysis.
                (index into expected times for video at which strongest correlation (lowest variance) is found, 
                list of expected times for video, 
                list of (diff, err) for the best match, corresponding to the individual time differences and each one's error bound) 
            
    """
    observed, expectedTimesSecs = test
    
    # convert to be on the sync timeline
    expected = [ startSyncTime + tickRate * t for t in expectedTimesSecs ]
    
    matchIndex, allTimeDifferencesAndErrors = correlate(expected, observed)
    timeDifferencesAndErrorsForMatch = allTimeDifferencesAndErrors[matchIndex]
    
    return (matchIndex, expected, timeDifferencesAndErrorsForMatch)





def runDetection(detector, channels, dueStartTimeUsecs, dueFinishTimeUsecs):
    """\
    
    for each channel of sample data, detect the beep or flash timings
    
    :param detector beep / flash detector to use for the detection
    :param nActivePins number of arduino inputs that were read during sampling
    :param channels  the data channels for the sample data separated out per pin.  This is a
        list of dictionaries, one per sampled pin.
            A dictionary is { "pinName": pin name, "isAudio": true or false, 
                "min": list of sampled minimum values for that pin (each value is the minimum over a millisecond period)
                "max": list of sampled maximum values for that pin (each value is the maximum over same millisecond period) }
    :param dueStartTimeUsecs
    :param dueFinishTimeUsecs
    :return the detected timings 
        list of dictionaries
            A dictionary is { "pin": pin name, "observed": list of detected timings }
                where a detected timing is a tuple (centre time of flash or beep, error bounds) 
                in units of ticks of the synchronisation timeline
    
    """
    timings = []
    for channel in channels:
        isAudio = channel["isAudio"]
        if isAudio:
            func = detector.samplesToBeepTimings
        else:
            func = detector.samplesToFlashTimings
        eventDuration = channel["eventDuration"]
        timings.append({"pinName": channel["pinName"], "observed": func(channel["min"], channel["max"], dueStartTimeUsecs, dueFinishTimeUsecs, eventDuration)})
    return timings




if __name__ == '__main__':
    # unit tests in:
    #    ../tests/test_analyse.py
    pass
    