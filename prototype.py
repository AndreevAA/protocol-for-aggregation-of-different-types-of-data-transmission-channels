import socket
import threading
import random
import time


class VirtualChannel:
    def __init__(self, name, bandwidth, latency, loss_chance):
        self.name = name
        self.bandwidth = bandwidth  # Пропускная способность в Mbps
        self.latency = latency  # Задержка в ms
        self.loss_chance = loss_chance  # Вероятность потери пакета
        self.lock = threading.Lock()

    def transmit(self, data_size):
        with self.lock:
            # Эмуляция задержки канала
            time.sleep(self.latency / 1000.0)
            # Эмулируем возможность потери пакета
            if random.random() < self.loss_chance:
                print(f"[{self.name}] Потеря пакета")
                return False
            else:
                # Эмуляция задержки передачи, основанной на пропускной способности
                time_to_send = data_size / (self.bandwidth * 1024 * 1024 / 8)  # перевод в секунды
                time.sleep(time_to_send)
                print(f"[{self.name}] Успешная передача: {data_size} байт")
                return True


class Aggregator:
    def __init__(self, channels):
        self.channels = channels

    def aggregate_data_transfer(self, data_size):
        # Пример простого управления потоком, распределяем данные по каналам
        threads = []
        for channel in self.channels:
            # Разбиваем размеры пакетов случайным образом для демонстрации
            chunk_size = data_size // len(self.channels)
            thread = threading.Thread(target=channel.transmit, args=(chunk_size,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()
        print("Передача данных завершена.")


def simulate_network():
    # Создаем виртуальные каналы с разными характеристиками
    channel1 = VirtualChannel("Канал 1", 10, 50, 0.05)  # 10 Mbps, 50 ms, 5% потери
    channel2 = VirtualChannel("Канал 2", 5, 100, 0.1)  # 5 Mbps, 100 ms, 10% потери

    # Создаем агрегатор для управления этими каналами
    aggregator = Aggregator([channel1, channel2])

    # Пример передачи данных
    total_data_size = 5000000  # 5 MB
    aggregator.aggregate_data_transfer(total_data_size)


if __name__ == "__main__":
    simulate_network()