// esp32_wifi_emg.ino - OPTIONAL, do it last: same readings, sent over WiFi (UDP)
#include <WiFi.h>
#include <WiFiUdp.h>

const char* SSID = "YourWiFiName";        // EDIT
const char* PASS = "YourWiFiPassword";    // EDIT
const char* LAPTOP_IP = "192.168.1.50";   // EDIT: laptop's IP on the same WiFi (ipconfig / ifconfig)
const int UDP_PORT = 5005;
const int PINS[3] = {34, 35, 32};
const unsigned long PERIOD_US = 1000;
unsigned long nextTick;
WiFiUDP udp;
char pkt[1024]; int len = 0, count = 0;

void setup() {
  analogReadResolution(12); analogSetAttenuation(ADC_11db);
  WiFi.begin(SSID, PASS);
  while (WiFi.status() != WL_CONNECTED) delay(200);
  WiFi.setSleep(false);                   // lower delay
  nextTick = micros();
}

void loop() {
  if ((long)(micros() - nextTick) >= 0) {
    nextTick += PERIOD_US;
    len += snprintf(pkt + len, sizeof(pkt) - len, "%lu,%d,%d,%d\n", micros(),
                    analogRead(PINS[0]), analogRead(PINS[1]), analogRead(PINS[2]));
    if (++count == 20) {                  // send 20 samples per packet
      udp.beginPacket(LAPTOP_IP, UDP_PORT);
      udp.write((uint8_t*)pkt, len);
      udp.endPacket();
      len = 0; count = 0;
    }
  }
}
