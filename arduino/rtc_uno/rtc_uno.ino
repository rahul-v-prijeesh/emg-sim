// rtc_uno.ino - Arduino Uno = the REAL-TIME CLOCK (RTC) unit of the project. That is its only job.
//
// Hardware: DS3231 RTC module on the Uno:  VCC -> 5V, GND -> GND, SDA -> A4, SCL -> A5
//           (nothing else is needed: no LEDs, no buttons, no SD card)
// Board:    Tools > Board > Arduino Uno.  Library: RTClib by Adafruit (Tools > Manage Libraries).
// Serial:   115200 baud over the USB cable to the laptop.
//
// What the laptop (live.py) can send, one line at a time (end of line = \n):
//   TIME?                       -> Uno replies   TIME 2026-10-17 12:42:00
//   SET 2026-10-17 12:42:00     -> sets the clock, replies   OK SET
//   REST / OPEN / CLOSE / PINCH / INDEX / FAULT
//                               -> if it is DIFFERENT from the previous word, the Uno replies
//                                  EVT,2026-10-17 12:42:00,OPEN
//                                  (the gesture, stamped with the RTC's date and time)
// At power-up the Uno prints  RTC OK  or  RTC FAILED  (and  RTC LOST POWER  if the coin cell
// was empty and the time must be set again).
//
// No String class and no delay(): fixed buffer, the loop never blocks.

#include <Wire.h>
#include <RTClib.h>

RTC_DS3231 rtc;
bool rtcOK = false;

const char* WORDS[] = {"REST", "OPEN", "CLOSE", "PINCH", "INDEX", "FAULT"};
const int N_WORDS = 6;
int lastWord = -1;

char buf[32];
byte n = 0;

void printStamp(const DateTime& t) {
  char s[24];
  snprintf(s, sizeof(s), "%04d-%02d-%02d %02d:%02d:%02d",
           t.year(), t.month(), t.day(), t.hour(), t.minute(), t.second());
  Serial.print(s);
}

void handleLine(const char* s) {
  if (strcmp(s, "TIME?") == 0) {
    if (!rtcOK) { Serial.println(F("ERR NO RTC")); return; }
    Serial.print(F("TIME ")); printStamp(rtc.now()); Serial.println();
    return;
  }
  if (strncmp(s, "SET ", 4) == 0) {
    int Y, M, D, h, m, sec;
    if (rtcOK && sscanf(s + 4, "%d-%d-%d %d:%d:%d", &Y, &M, &D, &h, &m, &sec) == 6 &&
        Y >= 2000 && Y <= 2099 && M >= 1 && M <= 12 && D >= 1 && D <= 31 &&
        h >= 0 && h <= 23 && m >= 0 && m <= 59 && sec >= 0 && sec <= 59) {
      rtc.adjust(DateTime(Y, M, D, h, m, sec));
      Serial.println(F("OK SET"));
    } else {
      Serial.println(F("ERR SET"));
    }
    return;
  }
  for (int i = 0; i < N_WORDS; i++) {
    if (strcmp(s, WORDS[i]) == 0) {
      if (i != lastWord) {                 // only report CHANGES, not every heartbeat
        lastWord = i;
        if (!rtcOK) { Serial.println(F("ERR NO RTC")); return; }
        Serial.print(F("EVT,")); printStamp(rtc.now());
        Serial.print(','); Serial.println(WORDS[i]);
      }
      return;
    }
  }
  // anything else is ignored
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { buf[n] = 0; handleLine(buf); n = 0; }
    else if (c == '\r') { /* ignore */ }
    else if (n < sizeof(buf) - 1) buf[n++] = c;
    else n = 0;                            // too long = garbage, start over
  }
}

void setup() {
  Serial.begin(115200);
  rtcOK = rtc.begin();
  Serial.println(rtcOK ? F("RTC OK") : F("RTC FAILED"));
  if (rtcOK && rtc.lostPower()) Serial.println(F("RTC LOST POWER - set the time with set_rtc.py"));
}

void loop() {
  readSerial();
}
