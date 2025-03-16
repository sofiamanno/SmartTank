# %%
import matplotlib.pyplot as plt
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt6.QtCore import QUrl, QTimer, pyqtSignal, QObject
import pandas as pd
import telebot
import requests
import time
from datetime import datetime
import logging
import numpy as np
import plotly
import threading
import sys

# Costanti per l'API
PARAMETRO_HTTP = "fill_level"
DEVICE_ID = "31ee4140-ff27-11ef-8e00-e370a74757c3"
BASE_URL = "https://demo.thingsboard.io/api/plugins/telemetry/DEVICE/"
# BASE_URL = "http://127.0.0.1:5000/tank_level"
THINGSBOARD_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJtbm5zZm8wMXM0OWMzNDJ4QHN0dWRpdW0udW5pY3QuaXQiLCJ1c2VySWQiOiIwMzNiNGM4MC1mZjI3LTExZWYtOGUwMC1lMzcwYTc0NzU3YzMiLCJzY29wZXMiOlsiVEVOQU5UX0FETUlOIl0sInNlc3Npb25JZCI6ImNlZTdhMTg5LTRmYmItNDJlOS1iMWE4LTliYjNiOWNlZjQ2YSIsImV4cCI6MTc0Mzc0NDkxNiwiaXNzIjoidGhpbmdzYm9hcmQuaW8iLCJpYXQiOjE3NDE5NDQ5MTYsImZpcnN0TmFtZSI6IlNvZmlhIiwibGFzdE5hbWUiOiJNYW5ubyIsImVuYWJsZWQiOnRydWUsInByaXZhY3lQb2xpY3lBY2NlcHRlZCI6dHJ1ZSwiaXNQdWJsaWMiOmZhbHNlLCJ0ZW5hbnRJZCI6IjAxYjNlOTMwLWZmMjctMTFlZi04ZTAwLWUzNzBhNzQ3NTdjMyIsImN1c3RvbWVySWQiOiIxMzgxNDAwMC0xZGQyLTExYjItODA4MC04MDgwODA4MDgwODAifQ.0KMLij0C79ABWXY5z-cYS3wQpoBpNB-c6cPdvTGTPGvP2LWwCHpwGqVzTyPZcRPxX53JHtjrDekqtaPQuUzd9w"
url = BASE_URL + DEVICE_ID + "/values/timeseries?keys=" + PARAMETRO_HTTP

HEADERS = {
    "Content-Type": "application/json",
    "X-Authorization": f"Bearer {THINGSBOARD_TOKEN}"
}

# Token Telegram
TELEGRAM_TOKEN = "7628326308:AAFXMzgOSmwUfQyvPS01T5MRMai0mhdSLZ8"
TELEGRAM_CHAT_ID = 1061541019
aleart_interval = 60 # secondi

# Configurazione del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TelegramBot:
    def __init__(self):
        self.bot =  telebot.TeleBot(TELEGRAM_TOKEN)
    
    def send_alert(self, message):
        self.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

class DataUpdater(QObject):
    data_received = pyqtSignal(dict)

    def update_data(self, data):
        self.data_received.emit(data)

class TankDataViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.telegram_bot = TelegramBot()
        # Inizializza la data dell'ultimo avviso inviato (1 gennaio 2000)
        self.alert_sent = datetime(2000, 1, 1)

        # Store each tank level value received 
        self.data_history = pd.DataFrame(columns=['tank_level', 'time'])

        self.setWindowTitle("Tank Data Viewer")
        self.setGeometry(100, 100, 400, 200)
        
        self.tank_title = QLabel("Tank Level Data")
        self.tank_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        
        self.tank_level_label = QLabel("Tank Level: N/A")
        self.last_time_label = QLabel("Last Update: N/A")
        self.empty_forecast = QLabel("Empty in: N/A")
        
        layout = QVBoxLayout()
        layout.addWidget(self.tank_title)
        layout.addWidget(self.tank_level_label)
        layout.addWidget(self.last_time_label)
        layout.addWidget(self.empty_forecast)
        
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)
        
        self.data_updater = DataUpdater()
        self.data_updater.data_received.connect(self.update_ui)
        
        self.request_thread = threading.Thread(
            target=request_data, 
            daemon=True, 
            kwargs={'updater':self.data_updater}
        )
        self.request_thread.start()
    
    def update_ui(self, data):
        current_time = datetime.now()
        if data['tank_level'] != 'N/A':
            print(data['tank_level'][0]['value'])
            tank_level = float(data['tank_level'][0]['value'])
            self.tank_level_label.setText(f"Tank Level: {tank_level:.2f}")
            self.last_time_label.setText(f"Last Update: {current_time}")

            # Store the data in the history
            self.data_history.loc[len(self.data_history)] = [tank_level, current_time]
            self.empty_forecast.setText(f"Empty in: {self.forecast_empty_tank()}")

            # Controlla se il livello è inferiore alla soglia e invia l'avviso ogni 60 secondi se necessario.
            if tank_level < 20 and (current_time - self.alert_sent).seconds > aleart_interval:
                self.alert_sent = current_time
                self.telegram_bot.send_alert(f"⚠️ Avviso: il livello della cisterna è sceso sotto 20! Attuale: {tank_level:.2f}")


    def forecast_empty_tank(self):
        """
        Calcola il tempo stimato in secondi per svuotare il serbatoio attraverso una regressione lineare.

        Returns:
            str: stringa da visualizzare nell'interfaccia utente
        """
        
        if len(self.data_history) < 3:
            return 'N/A'

        # Livello corrente del serbatoio
        current_level = self.data_history.at[len(self.data_history) - 1, 'tank_level']

        # Converte datetime in timestamp (secondi)
        timestamps = self.data_history['time'].astype('int64') // 10**9  
        m, q = np.polyfit(timestamps, self.data_history['tank_level'].to_list(), 1)

        # plt.plot(timestamps, self.data_history['tank_level'].to_list(), 'o')
        # plt.plot(timestamps, m*timestamps + q)
        # plt.show()

        if m >= 0:
            return 'N/A'
        
        empty_time = -current_level/m  # secondi

        if empty_time > 60:
            return f"{int(empty_time // 60)} minuti e {int(empty_time % 60)} secondi"
        else: 
            return f"{empty_time:.1f} secondi"  

        


def request_data(
    updater: DataUpdater,
):
    """
    Funzione che effettua una richiesta HTTP per recuperare i dati da thingsboard.
    """

    sleep_time = 2

    while True:
        try:
            response = requests.get(url, headers=HEADERS)
            # Raise an exception if the request fails
            response.raise_for_status()
            data = response.json()
            # tank_level = data.get(PARAMETRO_HTTP, [{}])[0].get('value')
            tank_level = data[PARAMETRO_HTTP]
            updater.update_data({
                'tank_level': tank_level,
                # 'last_time_tank_level': last_time_tank_level
            })
            logging.info(f"Tank level: {tank_level}")
        except Exception as e:
            updater.update_data({
                'tank_level': 'N/A',
                # 'last_time_tank_level': 'N/AA'
            })
            logging.info(f"Error while retrieving tank level: {e}")
        time.sleep(sleep_time)



if __name__ == "__main__":
    
    app = QApplication(sys.argv)
    window = TankDataViewer()
    window.show()
    sys.exit(app.exec())