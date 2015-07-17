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

Unit-tests for code that does statistics output
"""

import unittest

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/../src")


from stats import determineWithinTolerance
from stats import gapBetweenRanges


class Test_determineWithinTolerance(unittest.TestCase):

    def test_determineWithinTolerance(self):
    
        diffsAndErrors = [
            (10, 2),
            (3,  2),
            (-1, 3),
            (5,  3)
        ]
        
        tolerance = 15
        passFail,exceeds = determineWithinTolerance(diffsAndErrors, tolerance)
        self.assertEquals(passFail,True)
        self.assertEquals(exceeds, [0,0,0,0])

        tolerance = 3
        passFail,exceeds = determineWithinTolerance(diffsAndErrors, tolerance)
        self.assertEquals(passFail,False)
        self.assertEquals(exceeds, [5,0,0,0])

        diffsAndErrors = [
            (-20, 2),
            (-25, 3),
            (-18, 3),
            (-15, 3)
        ]
        
        tolerance = 15
        passFail,exceeds = determineWithinTolerance(diffsAndErrors, tolerance)
        self.assertEquals(passFail,False)
        self.assertEquals(exceeds, [-3,-7,0,0])


class Test_gapBetweenRanges(unittest.TestCase):

    def test_gapBetweenRanges(self):
        
        self.assertEquals(-5, gapBetweenRanges((0,10),(15,25)))
        self.assertEquals( 0, gapBetweenRanges((0,10),(9,20)))
        self.assertEquals( 2, gapBetweenRanges((20,30),(10,18)))
        

if __name__ == "__main__":

    unittest.main()
