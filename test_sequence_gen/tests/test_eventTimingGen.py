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
Unit-tests for eventTimingGen.py
"""

import sys
sys.path.append("../src")


import unittest
import itertools

from eventTimingGen import mls
from eventTimingGen import _mls_taps
from eventTimingGen import calcNearestDurationForExactNumberOfCycles
from eventTimingGen import genSequenceStartEnds
from eventTimingGen import genSequenceFromSampleIndices

class Test_mls(unittest.TestCase):

    def test_mls_non_repeating(self):
        """MLS sequence generator generates sequences that do not repeat prematurely."""

        for bitLen in _mls_taps:
            seen={}
            mlsGen = mls(bitLen, limitRepeats=2)
    
            register = 0
            mask = (2**bitLen) - 1
    
            # absorb first bitLen-1 bits to prime
            for i in range(0,bitLen-1):
                register = ((register << 1) | mlsGen.next()) & mask

            # now absorb next 2**bitLen-1 bits
            for i in range(0,2**bitLen -1):
                register = ((register << 1) | mlsGen.next()) & mask
                self.assertNotIn(register,seen, msg="MLS sequence generated for bitlength="+str(bitLen)+" does not repeat prematurely")
                seen[register] = True



class Test_calcNearestDurationForExactNumberOfCycles(unittest.TestCase):

    def test_simple(self):
    
        self.assertEquals(1,       calcNearestDurationForExactNumberOfCycles(1.0,     500))
        self.assertEquals(2.0/3.0, calcNearestDurationForExactNumberOfCycles(0.5,       3))
        self.assertEquals(0.0335,  calcNearestDurationForExactNumberOfCycles(1.0/30, 2000))


class Test_genSequenceStartEnds(unittest.TestCase):

    def test_genSequenceStartEnds(self):
    
        centreTimes = [ 1.0, 2.0, 5.0 ]
        unitsPerSecond = 1.0
        beepDuration = 0.2
        sampleRate = 1000
        
        expectedTimings = [ (900, 1100), (1900, 2100), (4900, 5100) ]
        
        timings = genSequenceStartEnds(centreTimes, beepDuration, unitsPerSecond, sampleRate)
        
        timings = list(timings)
        
        self.assertEquals(timings, expectedTimings)


class Test_genSequenceFromSampleIndices(unittest.TestCase):

    def test_genSequenceFromSampleIndices(self):
    
        startEndTimings = [ (10,15), (20,22) ]
        
        def gapGenFactory():
            while True:
                yield 0
                
        def eventGenFactory():
            return [1,2,3,4,5,6,7,8,9,10,11,12]
        
        gs=genSequenceFromSampleIndices(startEndTimings, gapGenFactory, eventGenFactory)
        data=list(itertools.islice(gs, 0, 30))
            
        self.assertEquals(data, [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 0, 0, 0, 0, 0, 1, 2, 0, 0, 0, 0, 0, 0, 0, 0])
        


if __name__ == "__main__":
    unittest.main()
