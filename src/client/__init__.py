# client.py
import asyncio
import hashlib
import struct
import time
import random
import logging
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Random import get_random_bytes

logging.basicConfig(level=logging.INFO)  # Настройка уровня логирования

class AggregatedClient:
    def __init__(self, server_address, channels):
        self.server_address = server_address  # Адрес сервера
        self.channels = channels  # Список каналов
        self.session_id = int(time.time())  # Уникальный идентификатор сессии
        self.segment_size = 1024  # Размер сегмента в байтах
        # Состояние каналов: задержка и пропускная способность
        self.channel_states = {ch['name']: {'latency': 0.0, 'bandwidth': 0.0} for ch in channels}
        self.retransmission_limit = 3  # Максимальное количество повторных попыток отправки
        self.encryption_key = get_random_bytes(16)  # Симметричный ключ AES

    async def send_data(self, data):
        logging.info(f"Начало отправки данных. Размер: {len(data)} байт")
        total_start_time = time.time()

        # Шифруем данные перед отправкой
        cipher = AES.new(self.encryption_key, AES.MODE_CBC)
        iv = cipher.iv  # Инициализационный вектор
        encrypted_data = cipher.encrypt(pad(data, AES.block_size))  # Шифрование с дополнением

        # Разбиваем зашифрованные данные на сегменты
        segments = [encrypted_data[i:i + self.segment_size] for i in range(0, len(encrypted_data), self.segment_size)]
        total_segments = len(segments)
        tasks = []

        # Отправляем ключ шифрования серверу
        await self.send_encryption_key(iv)

        for segment_number, segment in enumerate(segments):
            task = asyncio.create_task(
                self.send_segment(segment_number, total_segments, segment)  # Отправка каждого сегмента
            )
            tasks.append(task)

        await asyncio.gather(*tasks)  # Дожидаемся завершения отправки всех сегментов
        await self.send_fin_signal(total_segments)  # Отправляем сигнал завершения передачи

        total_end_time = time.time()
        logging.info(f"Отправка завершена. Общее время: {total_end_time - total_start_time:.2f} сек")

    async def send_encryption_key(self, iv):
        # Отправляем ключ шифрования и вектор инициализации по каждому каналу
        for channel in self.channels:
            try:
                reader, writer = await asyncio.open_connection(channel['host'], channel['port'])
                header = struct.pack('!I 4s', self.session_id, b'KEY')  # Заголовок сообщения
                data_length = struct.pack('!I', len(self.encryption_key) + len(iv))  # Длина данных
                writer.write(header + data_length + self.encryption_key + iv)  # Отправка ключа
                await writer.drain()  # Ожидание завершения отправки
                ack = await reader.read(4)  # Ожидание подтверждения
                if ack == b'ACK':
                    logging.info(f"[Канал {channel['name']}] Ключ шифрования отправлен успешно")
                else:
                    logging.error(f"[Канал {channel['name']}] Ошибка при отправке ключа шифрования")
            except Exception as e:
                logging.error(f"[Канал {channel['name']}] Ошибка при отправке ключа: {e}")
            finally:
                writer.close()  # Закрытие соединения
                await writer.wait_closed()

    async def send_segment(self, segment_number, total_segments, segment):
        retries = 0  # Счетчик повторных попыток
        success = False  # Флаг успешности отправки сегмента
        while retries < self.retransmission_limit and not success:
            channel = self.select_best_channel()  # Выбор лучшего канала
            try:
                start_time = time.time()
                reader, writer = await asyncio.open_connection(channel['host'], channel['port'])
                checksum = hashlib.sha256(segment).digest()  # Вычисление контрольной суммы
                header = struct.pack('!I I 32s', self.session_id, segment_number, checksum)  # Заголовок сегмента
                data_length = struct.pack('!I', len(segment))  # Длина сегмента
                writer.write(header + data_length + segment)  # Отправка сегмента
                await writer.drain()  # Ожидание завершения отправки
                ack = await reader.read(4)  # Ожидание подтверждения
                end_time = time.time()
                latency = end_time - start_time  # Измерение задержки
                bandwidth = len(segment) / latency  # Вычисление пропускной способности
                self.update_channel_state(channel['name'], latency, bandwidth)  # Обновление состояний канала
                if ack == b'ACK':
                    logging.info(f"[Канал {channel['name']}] Сегмент {segment_number + 1}/{total_segments} отправлен успешно")
                    success = True
                else:
                    logging.warning(f"[Канал {channel['name']}] NACK при отправке сегмента {segment_number + 1}")
                    retries += 1
            except Exception as e:
                logging.error(f"[Канал {channel['name']}] Ошибка: {e}")
                retries += 1
            finally:
                writer.close()  # Закрытие соединения
                await writer.wait_closed()

        if not success:
            logging.error(f"Не удалось отправить сегмент {segment_number + 1} после {self.retransmission_limit} попыток")

    async def send_fin_signal(self, total_segments):
        # Отправляем сигнал завершения передачи
        for channel in self.channels:
            try:
                reader, writer = await asyncio.open_connection(channel['host'], channel['port'])
                header = struct.pack('!I 4s', self.session_id, b'FIN')  # Заголовок завершения
                data_length = struct.pack('!I', 0)  # Длина данных
                writer.write(header + data_length)  # Отправка сигнала завершения
                await writer.drain()  # Ожидание завершения отправки
                ack = await reader.read(4)  # Ожидание подтверждения
                if ack == b'ACK':
                    logging.info(f"[Канал {channel['name']}] Сигнал завершения передачи отправлен успешно")
                else:
                    logging.error(f"[Канал {channel['name']}] Ошибка при отправке сигнала завершения передачи")
            except Exception as e:
                logging.error(f"[Канал {channel['name']}] Ошибка: {e}")
            finally:
                writer.close()  # Закрытие соединения
                await writer.wait_closed()

    def update_channel_state(self, channel_name, latency, bandwidth):
        # Обновляем информацию о задержке и пропускной способности канала
        self.channel_states[channel_name]['latency'] = latency
        self.channel_states[channel_name]['bandwidth'] = bandwidth

    def select_best_channel(self):
        # Выбор канала на основе задержки и пропускной способности
        def channel_score(ch):
            latency = self.channel_states[ch['name']]['latency'] or float('inf')
            bandwidth = self.channel_states[ch['name']]['bandwidth'] or 0.0
            return latency / (bandwidth + 1e-6)  # Рассчитываем оценку канала

        sorted_channels = sorted(self.channels, key=channel_score)  # Сортировка каналов по оценке
        return sorted_channels[0]  # Возвращаем канал с наилучшей оценкой

async def main():
    channels = [
        {'name': 'Channel1', 'host': '127.0.0.1', 'port': 8888},
        {'name': 'Channel2', 'host': '127.0.0.1', 'port': 8889},
    ]
    client = AggregatedClient(('127.0.0.1', 9000), channels)  # Создание клиента
    data = ('Данные для передачи ' * 1000).encode('utf-8')  # Данные для отправки
    await client.send_data(data)  # Отправка данных

if __name__ == '__main__':
    asyncio.run(main())  # Запуск основной функции