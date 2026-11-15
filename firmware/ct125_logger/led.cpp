#include "led.h"

#include "gps_task.h"
#include "logger_constants.h"
#include "logger_state.h"

static void blink(int times, uint32_t onMs, uint32_t offMs) {
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_LED, HIGH);
    vTaskDelay(pdMS_TO_TICKS(onMs));
    digitalWrite(PIN_LED, LOW);
    vTaskDelay(pdMS_TO_TICKS(offMs));
  }
}

static bool uploadSucceeded() {
  return lastUploadResult == UploadResult::Done || lastUploadResult == UploadResult::NothingToSend;
}

void ledTask(void *) {
  pinMode(PIN_LED, OUTPUT);
  for (;;) {
    if (mode == MODE_UPLOADING) {         // 送信中：1 秒ついて 1 秒消える
      blink(1, 1000, 1000);
    } else if (mode == MODE_IDLE && uploadSucceeded()) {  // 送信が終わった：つきっぱなし
      digitalWrite(PIN_LED, HIGH);
      vTaskDelay(pdMS_TO_TICKS(200));
    } else if (mode == MODE_IDLE) {       // 送れなかった：短く 3 回
      blink(3, 80, 150);
      vTaskDelay(pdMS_TO_TICKS(800));
    } else if (mode == MODE_WAIT_ADXL && waitUploadTried && uploadSucceeded()) {  // ADXL 待ち・送り終えた：つきっぱなし
      digitalWrite(PIN_LED, HIGH);
      vTaskDelay(pdMS_TO_TICKS(200));
    } else if (mode == MODE_WAIT_ADXL && waitUploadTried) {  // ADXL 待ち・送れなかった：短く 3 回
      blink(3, 80, 150);
      vTaskDelay(pdMS_TO_TICKS(800));
    } else if (mode == MODE_WAIT_ADXL) {  // ADXL を待っている：2 秒に 1 回、短く
      blink(1, 80, 1920);
    } else if (!running) {                // NG：速い点滅
      digitalWrite(PIN_LED, !digitalRead(PIN_LED));
      vTaskDelay(pdMS_TO_TICKS(100));
    } else if (gpsStatus == 'A') {        // 記録中・GPS 有効：ゆっくり点滅
      digitalWrite(PIN_LED, HIGH);
      vTaskDelay(pdMS_TO_TICKS(100));
      digitalWrite(PIN_LED, LOW);
      vTaskDelay(pdMS_TO_TICKS(900));
    } else {                              // 記録中・GPS まだ：短く2回
      for (int i = 0; i < 2; i++) {
        digitalWrite(PIN_LED, HIGH);
        vTaskDelay(pdMS_TO_TICKS(80));
        digitalWrite(PIN_LED, LOW);
        vTaskDelay(pdMS_TO_TICKS(150));
      }
      vTaskDelay(pdMS_TO_TICKS(540));
    }
  }
}
