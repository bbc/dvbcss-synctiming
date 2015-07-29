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
Code to calculate and print useful statistics about observed timings.

Usage:

Call the :func:`calcAndPrintStats` function to output statistics. Values supplied
must be in seconds.

"""


def calcAndPrintStats(matchIndex, allExpectedTimes, diffsAndErrors, toleranceSecs=None):
    """\
    Prints out statistics about the observed timings.

    :param matchIndex: Index into allExpectedTimes that the first observation matched up with
    :param allExpectedTimes: List of all expected times (units of seconds)
    :param diffsAnd Errors: List of tuples (diff, err) where diff is the
        offset between expected and observed (units of secs), and err is the
        error bound of measurement for that difference (also in units of secs)
    :param toleranceSecs: None, or a tolerance (in seconds) to be used in
        making a PASS/FAIL judgement on whether the observations were in sync.
        
    Offsets (difference values) are expected to be positive when the observation
    was early with respect to the expected time, and negative when it is late.
    
    :returns: Nothing. Output is printed to standard output.
    """
    
    diffs       = [diff for diff,err in diffsAndErrors]
    errorBounds = [err  for diff,err in diffsAndErrors]
    
    firstExpectedTime = allExpectedTimes[matchIndex]
    print "First observed flash/beep matched to one expected at %.3f seconds into the test video sequence. There were %d readings recorded." % (firstExpectedTime, len(diffs))
    
    avgOffsetMillis = secsToNearestMilli(calcMean(diffs))
    stdDevMillis    = secsToNearestMilli(calcVariance(diffs)**0.5)
    
    earlyLate = earlyLateString(avgOffsetMillis)
    
    minMillis = secsToNearestMilli(min(diffs))
    maxMillis = secsToNearestMilli(max(diffs))
    minEarlyLate = earlyLateString(minMillis)
    maxEarlyLate = earlyLateString(maxMillis)
    
    print ""
    print "Range of offsets between observed and expected:"
    print "    Lowest        : %7d   milliseconds %s" % (minMillis, minEarlyLate)
    print "    AVERAGE (mean): %7d   milliseconds %s" % (avgOffsetMillis, earlyLate)
    print "    Highest       : %7d   milliseconds %s" % (maxMillis, maxEarlyLate)
    print "    Std. deviation: %9.1f milliseconds" % stdDevMillis
    
    errMeanMillis = calcMean(errorBounds) * 1000.0
    errMinMillis  = min(errorBounds) * 1000.0
    errMaxMillis  = max(errorBounds) * 1000.0

    print
    print "Total measurement error bounds (range of uncertainty):"
    print "   Lowest        : %8.3f milliseconds" % errMinMillis
    print "   Average (mean): %8.3f milliseconds" % errMeanMillis
    print "   Highest       : %8.3f milliseconds" % errMaxMillis

    if toleranceSecs is not None:
        print ""
        print "Accuracy tolerance specified of %.3f milliseconds" % (toleranceSecs*1000.0)
        
        success, exceeds = determineWithinTolerance(diffsAndErrors, toleranceSecs)
        
        if success:
            print "    PASSED ... all observations within the tolerance interval"
            print "               (after taking into account measurement error bounds)"
        else:
            numFails = len([e for e in exceeds if e != 0])
            print "    FAILED ... %d of %d observations outside the tolerance interval" % (numFails, len(diffs))
            print "               (taking into account measurement error bounds)"
            print ""
            i=0
            for e in exceeds:
                i=i+1
                if e != 0:
                    eMillis = e*1000.0
                    earlyLate = earlyLateString(eMillis)
                    print "        Observation %d was outside tolerance and error margin by %.3f milliseconds %s" % (i, eMillis, earlyLate)
        print ""

def calcMean(data):
    """\
    Calculates statistical mean.
    :param data: List of values
    :returns: the mean of a list of values.
    """
    return sum(data)/float(len(data))
    
def calcVariance(data):
    """\
    Calculates statistical variance.
    :param data: List of values
    :returns: the variance of a list of values.
    """
    mean = calcMean(data)
    
    squaresDiff = sum([(value - mean)**2 for value in data])
    
    return squaresDiff / len(data)
    
def secsToNearestMilli(value):
    """\
    Return value converted to the nearest number of milliseconds
    :param value: seconds as a floating point number
    :return: value expressed in integer number of milliseconds (rounded)
    """
    return int(round(value * 1000))


def earlyLateString(value):
    if value > 0:
        return "(EARLY)"
    elif value < 0:
        return "(LATE)"
    else:
        return ""
        
        
def determineWithinTolerance(diffsAndErrors,tolerance):
    """\
    :returns: (passFail, exceeds) where passFail is a boolean indicating pass
    or failure, and exceeds is a list by the amount by which the tolerance
    was exceeded (minus the error bound). exceeds will contain only zeros in
    the event of a pass.
    """
    exceededErrorBy=[]
    allPassed = True
    for diff,errorBound in diffsAndErrors:
        minPossibleDiff = diff-errorBound
        maxPossibleDiff = diff+errorBound
        
        # check if the range -tolerance -> +tolerance overlaps with the
        # range of possible diffs. If so, then it is counted as a pass.
        # if not, then the observation was definitely outside the tolerance
        gap = gapBetweenRanges( (minPossibleDiff,maxPossibleDiff), (-tolerance,+tolerance) )
        if gap==0:
            exceededErrorBy.append(0)
        else:
            exceededErrorBy.append(gap)
            allPassed=False
            
    return allPassed, exceededErrorBy
    
def gapBetweenRanges(rangeA,rangeB):
    """\
    Returns the gap between two ranges of values, or zero if there is no gap.
    The sign of the returned value indicates which range is below the other.
    
    For example:
    * The gap between (0,10) and (15,25) is -5
    * The gap between (0,10) and (9,20) is 0
    * The gap between (20,30) and (10,18) is 2
    
    :param rangeA: a tuple (lo,hi) representing a range of values.
    :param rangeB: a tuple (lo,hi) representing a range of values.
    
    :returns: zero if two ranges overlap; otherwise the gap separating them.
        If rangeA is below range B then the value will be negative.
        If rangeA is above range B then the value will be positive.
    """
    aLo,aHi = rangeA
    bLo,bHi = rangeB
    
    if aLo > bHi:
        return aLo-bHi
    elif aHi < bLo:
        return aHi-bLo
    else:
        return 0
        
        
if __name__ == "__main__":

    print "-----------------------------------------------------------------------"
    print "Example of output when using calcAndPrintStats function in this module:"
    print "-----------------------------------------------------------------------"

    index = 1
    allExpectedTimes = [ 1.0, 2.0, 3.0, 4.0, 5.0, 6.0 ]
    diffsAndErrors = [
        (0.10, 0.05),
        (0.11, 0.05),
        (0.09, 0.05),
    ]
    toleranceSecs = 0.1
    calcAndPrintStats(index, allExpectedTimes, diffsAndErrors, toleranceSecs)
