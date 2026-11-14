// Boomerang counter lights - UNO R4 WiFi. Serial 9600, commands L:G / L:Y / L:R -> "ACK L:x"
#include "Arduino_LED_Matrix.h"
ArduinoLEDMatrix matrix;
const int G = 8, Y = 9, R = 10, BUZ = 11;      // external LEDs/buzzer (optional, from the kit)

byte CHECK[8][12] = {{0,0,0,0,0,0,0,0,0,0,0,0},{0,0,0,0,0,0,0,0,0,0,1,1},{0,0,0,0,0,0,0,0,0,1,1,0},{0,0,0,0,0,0,0,0,1,1,0,0},
                     {1,1,0,0,0,0,0,1,1,0,0,0},{0,1,1,0,0,0,1,1,0,0,0,0},{0,0,1,1,0,1,1,0,0,0,0,0},{0,0,0,1,1,1,0,0,0,0,0,0}};
byte DASH[8][12]  = {{0},{0},{0},{0,0,1,1,1,1,1,1,1,1,0,0},{0,0,1,1,1,1,1,1,1,1,0,0},{0},{0},{0}};
byte CROSS[8][12] = {{0,1,1,0,0,0,0,0,0,1,1,0},{0,0,1,1,0,0,0,0,1,1,0,0},{0,0,0,1,1,0,0,1,1,0,0,0},{0,0,0,0,1,1,1,1,0,0,0,0},
                     {0,0,0,0,1,1,1,1,0,0,0,0},{0,0,0,1,1,0,0,1,1,0,0,0},{0,0,1,1,0,0,0,0,1,1,0,0},{0,1,1,0,0,0,0,0,0,1,1,0}};

void show(int pin, byte frame[8][12]) {
  digitalWrite(G, LOW); digitalWrite(Y, LOW); digitalWrite(R, LOW);
  digitalWrite(pin, HIGH);
  matrix.renderBitmap(frame, 8, 12);
  if (pin == R) tone(BUZ, 880, 400);
}

void setup() {
  Serial.begin(9600);
  pinMode(G, OUTPUT); pinMode(Y, OUTPUT); pinMode(R, OUTPUT); pinMode(BUZ, OUTPUT);
  matrix.begin();
  show(G, CHECK); delay(400); show(Y, DASH); delay(400); show(R, CROSS); delay(400);  // self-test
  matrix.clear(); digitalWrite(R, LOW);
}

void loop() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd == "L:G") show(G, CHECK);
  else if (cmd == "L:Y") show(Y, DASH);
  else if (cmd == "L:R") show(R, CROSS);
  else { Serial.println("ERR " + cmd); return; }
  Serial.println("ACK " + cmd);
}