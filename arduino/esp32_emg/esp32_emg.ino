// esp32_emg.ino - reads 3 EMG sensors 1000 times per second and prints: micros,ch1,ch2,ch3
// Board: "ESP32 Dev Module". Serial Monitor / Python baud: 921600.
const int PINS[3] = {34, 35, 32};            // ADC1 pins
const unsigned long PERIOD_US = 1000;        // 1000 microseconds = 1000 samples per second
unsigned long nextTick;

void setup() {
  Serial.begin(921600);                      // fast, so 1000 lines per second fit easily
  analogReadResolution(12);                  // numbers from 0 to 4095
  analogSetAttenuation(ADC_11db);            // can read up to about 3.3 V
  nextTick = micros();
}

void loop() {
  if ((long)(micros() - nextTick) >= 0) {    // is it time for the next sample?
    nextTick += PERIOD_US;
    int a = analogRead(PINS[0]);
    int b = analogRead(PINS[1]);
    int c = analogRead(PINS[2]);
    Serial.printf("%lu,%d,%d,%d\n", micros(), a, b, c);
  }
}
