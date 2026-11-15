// Boomerang counter station - Arduino UNO Q, MCU side (STM32).
// Python on the Linux side calls show(code) over the Bridge:
//   0 = ready (idle)   1 = GREEN (tick)   2 = YELLOW (X)   3 = RED (X)   4 = cannot reach the backend (?)   5 = REVIEW (circle)
// The matrix is one colour only; the colour comes from the RGB LED and the onboard LED3.
// Onboard 8x13 matrix shows an icon, the onboard RGB LED (LED3) shows the colour, and optionally:
//   - ONE external RGB LED: green leg -> 220 ohm -> D8, red leg -> 220 ohm -> D10 (yellow = red + green),
//     longest (common) leg to GND (common cathode) or 3.3V (common anode, set RGB_COMMON_ANODE = true), or
//   - THREE separate LEDs on D8 green / D9 yellow / D10 red (set RGB_LED = false).
// Buzzer on D11. UNO Q header pins are 3.3 V: LEDs are a little dimmer than on a 5 V Uno, which is fine.
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

const int PIN_G = 8, PIN_Y = 9, PIN_R = 10, PIN_BUZ = 11;
const bool RGB_LED = true;                    // one RGB LED on D8 (green) + D10 (red); false = 3 separate LEDs
const bool RGB_COMMON_ANODE = false;          // true if the RGB LED's long leg goes to 3.3V (LOW = on)
const bool BUZZER_PASSIVE = false;            // true for a passive buzzer (no built-in oscillator)
const unsigned long HOLD_MS = 15000;          // keep a verdict on screen this long, then back to "ready"

Arduino_LED_Matrix matrix;

// .............   ...........##   ..........##.   .........##..   .##.....##...   ..##...##....   ...##.##.....   ....###......
uint8_t CHECK[104] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,1,1,0,0,0,0,0,1,1,0,0,0,0,0,1,1,0,0,0,1,1,0,0,0,0,0,0,0,1,1,0,1,1,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0};
uint8_t DASH[104] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,1,1,1,1,1,1,1,0,0,0,0,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
uint8_t CROSS[104] = {0,0,1,1,0,0,0,0,0,1,1,0,0,0,0,0,1,1,0,0,0,1,1,0,0,0,0,0,0,0,1,1,0,1,1,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0,0,1,1,0,1,1,0,0,0,0,0,0,0,1,1,0,0,0,1,1,0,0,0,0,0,1,1,0,0,0,0,0,1,1,0,0};
uint8_t BOX[104] = {0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,1,0,1,0,0,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,0,1,0,0,0,1,0,0,0,0,0,0,0,0,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
uint8_t QUESTION[104] = {0,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,1,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0};
uint8_t CIRCLE[104] = {0,0,0,0,0,1,1,1,0,0,0,0,0,0,0,0,1,1,0,0,0,1,1,0,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0,0,0,1,1,0,0,0,1,1,0,0,0,0,0,0,0,0,1,1,1,0,0,0,0,0};

volatile int pending = -1;          // set by the Bridge callback, handled in loop()
unsigned long shownAt = 0;
int current = 0;

// Buzzer pattern: list of on/off durations in ms, played without blocking loop().
unsigned long beepPattern[6];
int beepSteps = 0, beepIndex = 0;
unsigned long beepStepAt = 0, lastToggle = 0;
bool buzzLevel = false;

void setBeep(const unsigned long *steps, int n) {
  for (int i = 0; i < n; i++) beepPattern[i] = steps[i];
  beepSteps = n; beepIndex = 0; beepStepAt = millis();
}

void ext(int pin, bool on) {                  // external LED, honouring common-anode wiring
  bool level = (RGB_LED && RGB_COMMON_ANODE) ? !on : on;
  digitalWrite(pin, level ? HIGH : LOW);
}

void onboard(bool r, bool g) {                 // onboard RGB LED3 is active-low: LOW = on
  digitalWrite(LED3_R, r ? LOW : HIGH);
  digitalWrite(LED3_G, g ? LOW : HIGH);
  digitalWrite(LED3_B, HIGH);
}

void lights(int code) {
  bool green = code == 1, yellow = code == 2 || code == 4 || code == 5, red = code == 3;
  if (RGB_LED) {                               // yellow = red + green together
    ext(PIN_G, green || yellow);
    ext(PIN_R, red || yellow);
  } else {
    ext(PIN_G, green); ext(PIN_Y, yellow); ext(PIN_R, red);
  }
  onboard(red || yellow, green || yellow);
  switch (code) {
    case 1: matrix.draw(CHECK); break;
    case 2: matrix.draw(CROSS); break;      // YELLOW: X + yellow light
    case 3: matrix.draw(CROSS); break;      // RED: X + red light
    case 4: matrix.draw(QUESTION); break;
    case 5: matrix.draw(CIRCLE); break;     // REVIEW: circle + yellow light
    default: matrix.draw(BOX); break;
  }
  static const unsigned long GREEN_B[] = {80};
  static const unsigned long YELLOW_B[] = {120, 120, 120};
  static const unsigned long RED_B[] = {700};
  if (code == 1) setBeep(GREEN_B, 1);
  else if (code == 2 || code == 5) setBeep(YELLOW_B, 3);
  else if (code == 3) setBeep(RED_B, 1);
  current = code;
  shownAt = millis();
}

// Called from Python: Bridge.call("show", code). Runs between loop() passes (provide_safe).
void show(int code) { pending = code; }

void setup() {
  pinMode(PIN_G, OUTPUT); pinMode(PIN_Y, OUTPUT); pinMode(PIN_R, OUTPUT); pinMode(PIN_BUZ, OUTPUT);
  pinMode(LED3_R, OUTPUT); pinMode(LED3_G, OUTPUT); pinMode(LED3_B, OUTPUT);
  matrix.begin();
  matrix.setGrayscaleBits(1);
  // Self-test so you can see every light works before the backend is connected.
  lights(1); delay(400); lights(2); delay(400); lights(3); delay(400);
  digitalWrite(PIN_BUZ, LOW); beepSteps = 0;
  lights(0);
  Bridge.begin();                     // waits for the Linux side (arduino-router) to be up
  Bridge.provide_safe("show", show);
}

void loop() {
  if (pending >= 0) { int c = pending; pending = -1; lights(c); }
  unsigned long now = millis();

  // Back to "ready" after a while (keep the "?" error until the backend answers again).
  if (current != 0 && current != 4 && now - shownAt > HOLD_MS) lights(0);

  // Non-blocking buzzer: even steps sound, odd steps are silence.
  bool on = false;
  if (beepIndex < beepSteps) {
    if (now - beepStepAt >= beepPattern[beepIndex]) { beepIndex++; beepStepAt = now; }
    on = beepIndex < beepSteps && beepIndex % 2 == 0;
  }
  if (!on) { digitalWrite(PIN_BUZ, LOW); buzzLevel = false; }
  else if (!BUZZER_PASSIVE) digitalWrite(PIN_BUZ, HIGH);
  else if (micros() - lastToggle >= 250) {        // ~2 kHz square wave for a passive buzzer
    lastToggle = micros(); buzzLevel = !buzzLevel; digitalWrite(PIN_BUZ, buzzLevel ? HIGH : LOW);
  }
}
