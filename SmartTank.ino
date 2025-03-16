#include <WiFi101.h>
#include <WiFiClient.h>
#include <ArduinoJson.h>
#include <Ultrasonic.h>

#define SWITCH_PIN 7
#define MAX_HEIGHT 100.0  // Altezza massima della cisterna in cm

Ultrasonic ultrasonic(0);

// Credenziali WiFi
const char* ssid = "iPhone di Sofia";
const char* password = "sofia0911"; //!rete d
// ThingsBoard endpoint
const char* thingsboardServer = "demo.thingsboard.io";
const char* thingsboardPath = "/api/v1/dcXp1yB6Z3H5z29FQlGj/telemetry";

WiFiClient client;

void setup() {
    Serial.begin(115200);
    Serial.println("Avvio del programma...");
    
    pinMode(SWITCH_PIN, INPUT_PULLUP);
    
    Serial.println("Verifica presenza shield WiFi...");
    if (WiFi.status() == WL_NO_SHIELD) {
        Serial.println("WiFi shield non presente! Controlla il modulo MKR1000.");
        while (true) {}  // Blocco il codice se non c'è lo shield
    }

    Serial.println("Connessione al WiFi...");
    WiFi.begin(ssid, password);
    int wifi_attempts = 0;
    while (WiFi.status() != WL_CONNECTED && wifi_attempts < 20) {
        delay(1000);  
        Serial.print("Tentativo di connessione al WiFi... ");
        Serial.println(wifi_attempts + 1);
        wifi_attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("Connesso al WiFi!");
    } else {
        Serial.println("Connessione WiFi fallita.");
        while (true) {}  // Blocca il codice se non si connette
    }
}

void loop() {
    Serial.println("\n--- Nuovo ciclo loop() ---");

    int switchState = digitalRead(SWITCH_PIN);  // Leggi stato interruttore
    Serial.print("Stato interruttore: ");
    Serial.println(switchState);

    float fillPercentage = 0.0;
    
    if (switchState == 0) {  // Interruttore premuto → cisterna piena
        Serial.println("Cisterna piena al 100%");
        fillPercentage = 100.0;
    } else {  // Interruttore non premuto → calcolo livello
        Serial.println("Misurazione distanza...");
        float distance = ultrasonic.distanceRead();

        Serial.print("Distanza rilevata: ");
        Serial.print(distance);
        Serial.println(" cm");

        if (distance >= 500) {
            Serial.println("Sensore non funzionante, scartare dato.");
            return;
        } else {
            fillPercentage = (1 - (distance / MAX_HEIGHT)) * 100;
            fillPercentage = constrain(fillPercentage, 0, 100);
            Serial.print("Livello di riempimento: ");
            Serial.print(fillPercentage);
            Serial.println(" %");
        }
    }
    
    Serial.println("Invio dati a ThingsBoard...");
    sendTelemetry(fillPercentage);
    Serial.println("Dati inviati. Pausa di 2 secondi...");
    delay(2000);
}

void sendTelemetry(float fillLevel) {
    Serial.println("Preparazione dati per ThingsBoard...");

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi non connesso, impossibile inviare dati.");
        return;
    }
    
    if (!client.connect(thingsboardServer, 80)) {
        Serial.println("Connessione a ThingsBoard fallita.");
        return;
    }
    
    StaticJsonDocument<200> jsonDoc;
    jsonDoc["fill_level"] = fillLevel;
    
    String jsonData;
    serializeJson(jsonDoc, jsonData);
    
    Serial.print("Dati JSON da inviare: ");
    Serial.println(jsonData);
    
    String request = "POST " + String(thingsboardPath) + " HTTP/1.1\r\n";
    request += "Host: " + String(thingsboardServer) + "\r\n";
    request += "Content-Type: application/json\r\n";
    request += "Content-Length: " + String(jsonData.length()) + "\r\n\r\n";
    request += jsonData;
    
    client.print(request);
    Serial.println("Dati inviati a ThingsBoard.");
    
    client.stop();
}