// esp32_plotter_test.ino - just LOOK at your 3 sensors with Tools > Serial Plotter
// Board: "ESP32 Dev Module". Serial Plotter baud: 115200.
const int PINS[3] = {34, 35, 32};   // ADC1 pins: sensor 1, 2, 3

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);          // numbers from 0 to 4095
  analogSetAttenuation(ADC_11db);    // can read up to about 3.3 V
}

void loop() {
  Serial.printf("S1:%d,S2:%d,S3:%d\n", analogRead(PINS[0]), analogRead(PINS[1]), analogRead(PINS[2]));
  delay(10);                         // about 100 lines per second
}
