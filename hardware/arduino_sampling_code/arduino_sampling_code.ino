/*
 * Copyright 2015 British Broadcasting Corporation
 * 
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 * 
 *     http://www.apache.org/licenses/LICENSE-2.0
 * 
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * -------------------------------------------------------------------------
 * This code is intended to run on an Arduino Due
 *
 * It samples some, or all, of 4 analog input puts, recording the lowest and
 * highest value seen on each during consecutive 1 millisecond periods
 * for a duration of time.
 *
 * The sampling is commenced by a command sent via the native USB virtual-serial
 * connection. And the recorded data is relayed back that way. The arduino
 * also sends back the local time (read from the micros() function) at which
 * the sampling process started and ended.
 *
 * This code also responds to commands to configure which analog pins will
 * be sampled (or not)/
 *
 * This code also responds to a command to perform a simple clock synchronisation
 * similar to NTP request-response. When the command is received, the Arduino
 * immediately sends back the Arduino clock time (read from the micros()
 * function), so the sender of the original command can match that up with their
 * own local clock; taking into account the round-trip time.
 *
 */

#define N_INPUTS 4

#define FLASH_SENSOR_ANALOG_PIN_0 0
#define FLASH_SENSOR_ANALOG_PIN_1 2
#define AUDIO_INPUT_ANALOG_PIN_0 1
#define AUDIO_INPUT_ANALOG_PIN_1 3

#define LEDPIN 13


/* map from a pin request command to analog pin number
 */
int pinMap[4] = {
    FLASH_SENSOR_ANALOG_PIN_0,  /* cmd '0' */
    AUDIO_INPUT_ANALOG_PIN_0,   /* cmd '1' */
    FLASH_SENSOR_ANALOG_PIN_1,  /* cmd '2' */
    AUDIO_INPUT_ANALOG_PIN_1    /* cmd '3' */
};

/* the following array indicates which pins are to be enabled.
 * if enable[i] is true, then the analog pin given by pimMap[i] is to be sampled.
 * this gets updated as the commands '0' to '3' are received, prior to the command
 * that initiates the continuous sampling
 */
int enable[4];
    
/* here's the number of pins the client has requested to be sampled.
 * if the client gave the commands '3' then '1', then the number of pins to be sampled
 * is 2.  nActivePorts indicates how many non-zero entries are present in the enable[] array
 */
int nActivePorts;

/* when the command is given to start the continuous sampling, the "enable" array
 * is processed in order, from index 0 to 3.  If enable[i] is true, then pinMap[i]
 * is copied into the next free slot in activePort (thus populating entries from 0 to
 * nActivePorts - 1) 
 */
int activePort[4];

/* the number of blocks we have available within the sample buffer
 * depends how many pins are requested to be sampled.  Each pin requires
 * BLKSIZE_PER_PIN bytes per block.  One block will hold the high and low values sampled
 * for each pin, within one millisecond.  One pin's data is stored in ascending char addresses
 * as "high" value, then "low" value, as observed over a millisecond.  0 to
 * (nActivePorts - 1) BLKSIZE_PER_PIN byte blocks are stored for that millisecond.  These BLKSIZE_PER_PIN byte blocks
 * are written out starting with the sample data read from activePort[0], then for
 * activePort[1], etc.
 */ 
int nMilliBlks;


/* here's the number of bytes we need to store per pin, to represent the low and high
 * values found over a 1 ms period
 */
#define BLKSIZE_PER_PIN 2
#define NINETY_KB (90 * 1024)

/* here's our sample buffer, consisting of a sequence of 2-byte blocks ...
 * One block will hold the high and low values found while continuously sampling
 * a pin over a one millisecond period.  One pin's block is stored in ascending char addresses
 * as "high" value, then "low" value.  0 to
 * (nActivePorts - 1) blocks are stored for that millisecond.
 * these blocks are are written out starting with the block corresponding to activePort[0], then for
 * activePort[1], etc.
 */ 
unsigned char* rawData;

void doinit();
unsigned int nextMillisBoundary();
void capture();
void doBulkTransfer();
int setupActivePortsMapping();
int samePeriod(unsigned int periodStart);
void initLoHi();
void initHiLoDetection(int whichPeriod);
void findHiLo(int index);
void writeInt(int x);
void writeUInt(unsigned int x);
void flashLed(int n);
void measureUART();
void prepareToCapture();

/* ---------------------------------------------------------------------
   arduino code entry points
   ---------------------------------------------------------------------
*/

void setup() {
  analogReadResolution(8);
  rawData = (unsigned char*)malloc(NINETY_KB);
  doinit();
  SerialUSB.begin(2304200);
  pinMode(LEDPIN, OUTPUT);
  if (rawData == NULL) {
      flashLed(5,800);
  } else {
  	flashLed(5, 300);
  }
}


/**
 * clear down the enable flags, so no continuous sampling will occur if requested
**/
void doinit() {
    nActivePorts = 0;
    for (int i=0; i<4; i++) {
        enable[i] = 0;
    }
}

void loop() {
  int idx;
  int rcvTime;
    while (1) {
      if (SerialUSB.available()) {
        /* respond to any command immediately with a local time measurement */
        writeInt(micros());
        SerialUSB.flush();       
        int opcode = SerialUSB.read();
        switch (opcode) {
        case '0':
        case '1':
        case '2':
        case '3':
            idx = opcode-'0';
            enable[idx] = 1;
            break;
        case '4':
            prepareToCapture();
            break;      
        case 'S':
            capture();
            break;           
        case 'B':
           	doBulkTransfer();
           	break;
        case 'T':
        	/* timing command .. handled at top of loop */
           	break;    
        }
       SerialUSB.flush();
     }
  }
}


void flashLed(int n, int delayMs) {
  for (int i=0; i<n; i++) {
    digitalWrite(LEDPIN, LOW);
    delay(delayMs);
    digitalWrite(LEDPIN, HIGH);
    delay(delayMs);
 }
}


/**
 * prepare for a burst of pin sampling.  Compute how many
 * blocks will be created by the capture, based on the number
 * of ports chosen for sampling by the client, and initialise
 * the static block of memory with high,low value pairs
 */
void prepareToCapture() {
    nActivePorts = setupActivePortsMapping();
    if (nActivePorts == 0 || nActivePorts > N_INPUTS) {
        doinit();
        writeInt(0);
        writeInt(0);
        return;
    }
    /* we need BLKSIZE_PER_PIN bytes of data per active analogue pin per millisecond
     * and we are going to limit ourselves to 90KB total
     */
    nMilliBlks = NINETY_KB / (nActivePorts * BLKSIZE_PER_PIN);
    initLoHi();
    writeInt(nActivePorts);
    writeInt(nMilliBlks);
  }

/**
 * Sample the ports chosen by client, via the '0' to '3' commands.
 * For each such port, determine high and low values over continuous sampling during 1 millisec,
 * and store this discovered pair of results.  This represents one data sample. Do this over a
 * period of time that will keep us within 90 KB of RAM consumption (Arduino Due has 96 KB available) 
**/
void capture() {

#define UINT_32_MAX ((unsigned int)(0xffffffff))
#define UINT_32_NEG ((unsigned int)(0x80000000))

    unsigned int startOfCurrentPeriod;
    unsigned int startOfNextPeriod;
    unsigned int startTime;
    
    startTime = startOfCurrentPeriod = micros();
    startOfNextPeriod = startOfCurrentPeriod + 1000;

    for (int period=0; period < nMilliBlks; period++) {
        unsigned int now = micros();
        while (((startOfNextPeriod - now) & UINT_32_MAX) < UINT_32_NEG) {
           findHiLo(period);
           now = micros();
        }
        startOfCurrentPeriod = startOfNextPeriod;
        startOfNextPeriod = startOfCurrentPeriod + 1000;
    }

    int endTime = micros();
    writeInt(startTime);    
    writeInt(endTime);
    writeInt(nMilliBlks);
    SerialUSB.flush();
 }


/**
 * initialise entire raw data area.
**/
void initLoHi() {
    for (int n=0; n<nMilliBlks; n++) {
        initHiLoDetection(n);
    }
}

/**
 * initialise the data blocks for holding the high and low values observed
 * during one millisecond across all active ports (see initLoHi())
 * @param whichPeriod which millisecond period we're about to start sampling for
 * (0 is the first period)
**/
void initHiLoDetection(int whichPeriod) {
    int offs = whichPeriod * nActivePorts * BLKSIZE_PER_PIN;
    for (int i = 0; i < nActivePorts; i++) {
        /* initialise the "high" value */
        rawData[offs++] = 0;
        /* initialise the "low" value */
        rawData[offs++] = 0xff;
    }
}

/**
 * sample each active analog pin, and update its hi/lo values 
 * for this current period, if needed
 * @param index which millisecond period we're about to start sampling for
 * (0 is the first period)
**/
void findHiLo(int index) {
    int offs = index * nActivePorts * BLKSIZE_PER_PIN;
    for (int i = 0; i < nActivePorts; i++) {
        unsigned char sample = (unsigned char) analogRead(activePort[i]);
        /* update the "high" value first */
        if (sample > rawData[offs]) {
            rawData[offs] = sample;
        } 
        /* update the "low" value next */
        offs++;
        if (sample < rawData[offs]) {
            rawData[offs] = sample;
        } 
        offs++;
    }
}


/**
 * initialise array which shows which analogue pins are to be sampled
 * @return: number of analogues pins requested by client
**/
int setupActivePortsMapping() {
    int nActive = 0;
    for (int i=0; i<4; i++) {
        if (enable[i]) {
            activePort[nActive] = pinMap[i];
            nActive++;
        }
    }
    return nActive;   
}

/**
 * send samples back to client
**/
void doBulkTransfer() {
    int nbytes = nMilliBlks * nActivePorts * BLKSIZE_PER_PIN;
    writeUInt(nbytes);
    for (int i=0; i < nbytes; i++) {
        SerialUSB.write(rawData[i]);
    }
    SerialUSB.flush();
    
    /* prepare for any further runs */
    initLoHi();
    doinit();
 }


/* ---------------------------------------------------------------------
   Serial data writing
   ---------------------------------------------------------------------
*/

void writeInt(int x) {
   SerialUSB.write( (x >> 24) & 0xff );
   SerialUSB.write( (x >> 16) & 0xff );
   SerialUSB.write( (x >> 8 ) & 0xff );
   SerialUSB.write( (x      ) & 0xff );
}

void writeUInt(unsigned int x) {
   SerialUSB.write( (x >> 24) & 0xff );
   SerialUSB.write( (x >> 16) & 0xff );
   SerialUSB.write( (x >> 8 ) & 0xff );
   SerialUSB.write( (x      ) & 0xff );
}

