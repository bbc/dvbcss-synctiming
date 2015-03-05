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


class DispersionRecorder(object):

    def __init__(self, dispersionAlgorithm):
        """\
        :param dispersionAlgorithm: The algorithm object to obtain dispersions from.
        
        The algorithm object must have an onClockAdjusted method that can be overriden or replaced
        with the same arguments as the one defined for :class:`~dvbcss.protocol.client.wc.algorithm.LowestDispersionCandidate`.
        
        Works by replacing the onClockAdjusted method in the algorithm object,
        so beware if using other code that tries to do the same.
        
        Usage:
        
        .. code-block:: python
        
            algorithm = LowestDispersionAlgorithm(...)
            
            ... create a wall clock client that uses this algorithm object ...
        
            recorder = DispersionRecorder(algorithm)
            
            ...
            
            recorder.start()
            
            ...
            
            recorder.stop()   # not necessary, but will stop memory being filled!
            
            
            t=int(raw_input("Enter a wall clock time:"))
            disp = recorder.dispersionAt(t)
            print "At wall clock time "+str(t)+", the dispersion was:",disp
            
        """
        super(DispersionRecorder,self).__init__()
        self.changeHistory = []
        self.recording = False
        self.algorithm = dispersionAlgorithm
        
        # plug into the algorithm object to receive the onClockAdjusted calls
        self.original_onClockAdjusted = self.algorithm.onClockAdjusted
        self.algorithm.onClockAdjusted = self._onClockAdjustedHandler
        
        
    def _onClockAdjustedHandler(self, timeAfterAdjustment, adjustment, oldDispersionNanos, newDispersionNanos, dispersionGrowthRate):
        if self.recording:
            entry = timeAfterAdjustment, adjustment, oldDispersionNanos, newDispersionNanos, dispersionGrowthRate
            self.changeHistory.append(entry)
            
        self.original_onClockAdjusted(timeAfterAdjustment, adjustment, oldDispersionNanos, newDispersionNanos, dispersionGrowthRate)
            
            
    def clear(self):
        """\
        Clear the recorded history.
        """
        self.changeHistory = []
        
        
    def start(self):
        """\
        Start recording changes in dispersion.
        
        If already recording, then this method call does nothing.
        """
        self.recording = True
        
        
    def stop(self):
        """\
        Stop recording changes in dispersion.
        
        If already not recording, then this method call does nothing.
        """
        self.recording = False
    
    
    def dispersionAt(self, wcTime):
        """\
        Calculate the dispersion at a given wall clock time, using the recorded history.
        
        :param wcTime: time of the wall clock
        :returns: dispersion (in nanoseconds) when the wall clock had the time specified
        """
        
        changeInfo = None
        for ci in self.changeHistory:
            when = ci[0]
            if when <= wcTime:
                changeInfo = ci
            else:
                pass # don't abort immediately but instead
                # keep looking through because, due to clock adjustment we
                # might get a later recorded history entry that covers the
                # same range of wall clock values (because the clock could jump
                # backwards when adjusted)
        
        if changeInfo is None:
            raise ValueError("History did not contain any entries early enough to give dispersion at time "+str(wcTime))
        
        # unpack    
        when, adjustment, oldDispersionNanos, newDispersionNanos, dispersionGrowthRate = changeInfo
        
        # 'when' is before 'wcTime'
        # so we extrapolate the newDispersion
        timeDiff = wcTime - when
        dispersion = newDispersionNanos + dispersionGrowthRate * timeDiff
        
        return dispersion


