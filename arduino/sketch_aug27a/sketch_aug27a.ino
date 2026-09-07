// Array untuk 8 pin analog (Pastikan pakai board Nano Every/Mega yang punya 8 pin)
const int flexPins[8] = { A0, A1, A2, A3, A4, A5, A6, A7 };

float VCC = 5.0;     // Tegangan Arduino
float R2 = 10000.0;  // Resistor pembagi tegangan (10K Ohm)

// =========================================================================
// ARRAY KALIBRASI INDIVIDU UNTUK MASING-MASING SENSOR (S1 sampai S8)
// Ubah nilai-nilai di bawah ini sesuai hasil kalibrasi riil dari setiap sensor Anda!
// =========================================================================

// Nilai hambatan (Ohm) saat sensor BENAR-BENAR LURUS (flat)
float sensorMinResistance[8] = { 
  29960.5, // Sensor 1
  31926.10, // Sensor 2 (Contoh jika sedikit berbeda)
  27472.2, // Sensor 3
  28029.7, // Sensor 4
  33164.4, // Sensor 5
  35669.0, // Sensor 6
  31417.8, // Sensor 7
  30756.8  // Sensor 8
};

// Nilai hambatan (Ohm) saat sensor DITEKUK 90 DERAJAT (maksimal)
float sensorMaxResistance[8] = { 
  26535.70, // Sensor 1
  29195.41, // Sensor 2 (Contoh jika sedikit berbeda)
  25397.66, // Sensor 3
  26405.58, // Sensor 4
  29498.87, // Sensor 5
  34285.22, // Sensor 6
  29498.34, // Sensor 7
  27610.5  // Sensor 8
};

void setup() {
  Serial.begin(115200);
  Serial.println("Memulai pembacaan 8 Sensor Flex (Kalibrasi Per-Sensor)...");
  Serial.println("========================================================");
}

void loop() {
  for (int i = 0; i < 8; i++) {
    int ADCRaw = analogRead(flexPins[i]);

    if (ADCRaw == 0) {
      ADCRaw = 1;
    }

    // 1. Menghitung Tegangan (Voltage)
    float ADCVoltage = (ADCRaw * VCC) / 1023.0;

    // 2. Menghitung Resistansi asli (Ohm)
    float Resistance = R2 * (VCC / ADCVoltage - 1.0);

    // 3. Menghitung Sudut (0 - 90 Derajat) menggunakan rumus Float
    float Sudut = (Resistance - sensorMinResistance[i]) * 180.0 / (sensorMaxResistance[i] - sensorMinResistance[i]);
    
    // Memastikan nilai sudut tidak bablas di bawah 0 atau di atas 90 derajat
    if (Sudut < 0.0) Sudut = 0.0;
    if (Sudut > 180.0) Sudut = 180.0;

    // Cetak ketiga nilai berurutan: Ohm, Volt, Sudut
    Serial.print(Resistance);
    Serial.print(",");
    Serial.print(ADCVoltage);
    // Serial.print(",");
    // Serial.print(Sudut);

    // Cetak koma pemisah antar sensor (jangan di sensor ke-8)
    if (i < 7) {
      Serial.print(","); 
    }
  }

  Serial.println();  // Pindah baris
  delay(100);        // Delay dinaikkan sedikit agar 24 data tidak bertabrakan
}