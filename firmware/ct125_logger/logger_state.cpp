#include "logger_state.h"

volatile Mode mode = MODE_ERROR;
volatile UploadResult lastUploadResult = UploadResult::NothingToSend;

RingbufHandle_t ringAccel, ringGps, ringEvent;

volatile uint32_t samples = 0, ringDrops = 0, fifoOverruns = 0, i2cErrors = 0, sdWriteErrors = 0;
volatile uint64_t bytesWritten = 0;
volatile int64_t firstSampleUs = -1, lastSampleUs = -1;
bool running = false;

volatile bool stopRequested = false, accelStopped = false, gpsStopped = false;
volatile bool hasMoved = false;
