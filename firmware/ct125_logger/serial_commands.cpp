#include "serial_commands.h"

#include <SD.h>

#include "config_store.h"

bool uploadRequestedBySerial = false;

static void printUploadLog() {
  File f = SD.open("/upload_log.csv");
  if (!f) {
    Serial.println("LOG (no /upload_log.csv)");
    return;
  }
  const size_t tailBytes = 4096;  // 最後の約 40 行
  if (f.size() > tailBytes) {
    f.seek(f.size() - tailBytes);
    f.readStringUntil('\n');  // 途中から始まる行は捨てる
  }
  while (f.available()) Serial.printf("LOG %s\n", f.readStringUntil('\n').c_str());
  f.close();
  Serial.println("LOG_END");
}

void pollSerial() {
  static String line;
  while (Serial.available()) {
    char c = Serial.read();
    if (c != '\n') {
      if (line.length() < 300) line += c;
      continue;
    }
    line.trim();
    if (line == "UPLOAD") uploadRequestedBySerial = true;
    else if (line == "LOG") printUploadLog();
    else if (line.length()) handleConfigCommand(line);
    line = "";
  }
}
