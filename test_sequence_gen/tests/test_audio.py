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
Unit-tests for audio.py
"""

import sys
sys.path.append("../src")


import unittest

from audio import GenTone


# ---------------------------------------------------------------------------

class Test_genTone(unittest.TestCase):

    def test_tone(self):
    
        sampleRate = 1000
        peakValue = 1.0
        toneHz = 250
        phaseOffsetCycles = 0.0
        tg = GenTone(sampleRate, peakValue, toneHz, phaseOffsetCycles)
        
        for i in range(0,10000):
            self.assertAlmostEquals(tg.next(),  0.0, places=15)
            self.assertAlmostEquals(tg.next(),  1.0, places=15)
            self.assertAlmostEquals(tg.next(),  0.0, places=15)
            self.assertAlmostEquals(tg.next(), -1.0, places=15)

        phaseOffsetCycles = 0.25
        tg = GenTone(sampleRate, peakValue, toneHz, phaseOffsetCycles)
        
        for i in range(0,10000):
            self.assertAlmostEquals(tg.next(),  1.0, places=15)
            self.assertAlmostEquals(tg.next(),  0.0, places=15)
            self.assertAlmostEquals(tg.next(), -1.0, places=15)
            self.assertAlmostEquals(tg.next(),  0.0, places=15)
    

 
if __name__ == "__main__":
 
    unittest.main()
    