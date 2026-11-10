#include "nmea.h"

String nmeaField(const String &s, int n) {
  int start = 0;
  for (int i = 0; i < n; i++) {
    start = s.indexOf(',', start);
    if (start < 0) return "";
    start++;
  }
  int end = s.indexOf(',', start);
  int star = s.indexOf('*', start);
  if (end < 0 || (star >= 0 && star < end)) end = star;
  return s.substring(start, end < 0 ? s.length() : end);
}

String nmeaDeg(const String &v, const String &hemi) {
  if (v.length() < 4) return "";
  double x = v.toDouble();
  int d = (int)(x / 100);
  double deg = d + (x - d * 100) / 60.0;
  if (hemi == "S" || hemi == "W") deg = -deg;
  char b[16];
  snprintf(b, sizeof(b), "%.7f", deg);
  return b;
}

bool nmeaChecksumOk(const String &s) {
  int star = s.indexOf('*');
  if (!s.startsWith("$") || star < 0) return false;
  uint8_t c = 0;
  for (int i = 1; i < star; i++) c ^= s[i];
  return strtol(s.substring(star + 1).c_str(), nullptr, 16) == c;
}
