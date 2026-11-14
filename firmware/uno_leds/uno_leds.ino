// Boomerang counter lights - Arduino UNO R4 WiFi
// Serial 9600 baud, newline-ended commands: L:G  L:Y  L:R   -> replies "ACK L:x"
// Wiring: D8 green, D9 yellow, D10 red (each via 220 ohm to GND), buzzer + on D11.
const int G = 8, Y = 9, R = 10, BUZ = 11;

void show(int pin) {
  digitalWrite(G, LOW); digitalWrite(Y, LOW); digitalWrite(R, LOW);
  digitalWrite(pin, HIGH);
  if (pin == R) tone(BUZ, 880, 400);
}

void setup() {
  Serial.begin(9600);
  pinMode(G, OUTPUT); pinMode(Y, OUTPUT); pinMode(R, OUTPUT); pinMode(BUZ, OUTPUT);
  show(Y); delay(300); show(G); delay(300); digitalWrite(G, LOW);  // power-on self test
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "L:G") show(G);
    else if (cmd == "L:Y") show(Y);
    else if (cmd == "L:R") show(R);
    else { Serial.println("ERR " + cmd); return; }
    Serial.println("ACK " + cmd);
  }
}
