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

"""
Unit-tests for dispersion history recorder code
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/../src")


from dispersion import DispersionRecorder


import unittest


class Mock_Algorithm(object):

    def onClockAdjusted(self, timeAfterAdjustment, adjustment, oldDispersionNanos, newDispersionNanos, dispersionGrowthRate):
        pass
        

class Test_DispersionRecorder(unittest.TestCase):

    def test_plugsInCorrectly(self):
    
        algorithm = Mock_Algorithm()
        oldHookValue = algorithm.onClockAdjusted
        
        recorder = DispersionRecorder(algorithm)
        self.assertNotEquals(oldHookValue, algorithm.onClockAdjusted)
    
    
    def test_notInitiallyRecording(self):
    
        algorithm = Mock_Algorithm()
        recorder = DispersionRecorder(algorithm)

        algorithm.onClockAdjusted( 1000, 0, 0, 100, 1 )
            
        self.assertRaises(ValueError, recorder.dispersionAt, 1001)


    def test_recordsSimple(self):

        algorithm = Mock_Algorithm()
        recorder = DispersionRecorder(algorithm)
        recorder.start()

        algorithm.onClockAdjusted( 1000, 0, 0, 100, 2 )

        self.assertEquals(102, recorder.dispersionAt(1001))


    def test_errorIfToEarly(self):

        algorithm = Mock_Algorithm()
        recorder = DispersionRecorder(algorithm)
        recorder.start()

        algorithm.onClockAdjusted( 1000, 0, 0, 100, 2 )
            
        self.assertRaises(ValueError, recorder.dispersionAt, 999)


    def test_multipleHistoryEntries(self):

        algorithm = Mock_Algorithm()
        recorder = DispersionRecorder(algorithm)
        recorder.start()

        algorithm.onClockAdjusted( 1000, 0,     0, 100, 2 )
        algorithm.onClockAdjusted( 2000, 3,  1994, 110, 2 )
        algorithm.onClockAdjusted( 3000, -2, 2114,  90, 3 )

        self.assertEquals( 100+  2, recorder.dispersionAt(1001))
        self.assertEquals( 100+100, recorder.dispersionAt(1050))
        self.assertEquals( 110+ 12, recorder.dispersionAt(2006))
        self.assertEquals(  90+  9, recorder.dispersionAt(3003))


if __name__ == "__main__":

    unittest.main()
