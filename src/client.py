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
import time

logging.basicConfig(level=logging.INFO)

class AggregatedClient:
    def __init__(self, server_address, channels):
        self.server_address = server_address
        self.channels = channels  # Список каналов
        self.session_id = int(time.time())  # Уникальный идентификатор сессии
        self.segment_size = 1024  # Размер сегмента в байтах
        self.channel_states = {ch['name']: {'latency': 0.0, 'bandwidth': 0.0} for ch in channels}
        self.retransmission_limit = 3
        self.encryption_key = get_random_bytes(16)  # Симметричный ключ AES

    async def send_data(self, data):
        logging.info(f"Начало отправки данных. Размер: {len(data)} байт")
        total_start_time = time.time()

        # Шифруем данные
        cipher = AES.new(self.encryption_key, AES.MODE_CBC)
        iv = cipher.iv
        encrypted_data = cipher.encrypt(pad(data, AES.block_size))

        # Разбиваем на сегменты
        segments = [encrypted_data[i:i + self.segment_size] for i in range(0, len(encrypted_data), self.segment_size)]
        total_segments = len(segments)
        tasks = []

        # Отправляем ключ шифрования серверу
        await self.send_encryption_key(iv)

        for segment_number, segment in enumerate(segments):
            task = asyncio.create_task(
                self.send_segment(segment_number, total_segments, segment)
            )
            tasks.append(task)

        await asyncio.gather(*tasks)
        # Отправляем сигнал завершения передачи
        await self.send_fin_signal(total_segments)

        total_end_time = time.time()
        logging.info(f"Отправка завершена. Общее время: {total_end_time - total_start_time:.2f} сек")

    async def send_encryption_key(self, iv):
        # Отправляем ключ шифрования и вектор инициализации серверу по каждому каналу
        for channel in self.channels:
            try:
                reader, writer = await asyncio.open_connection(channel['host'], channel['port'])
                header = struct.pack('!I 4s', self.session_id, b'KEY')
                data_length = struct.pack('!I', len(self.encryption_key) + len(iv))
                writer.write(header + data_length + self.encryption_key + iv)
                await writer.drain()
                ack = await reader.read(4)
                if ack == b'ACK':
                    logging.info(f"[Канал {channel['name']}] Ключ шифрования отправлен успешно")
                else:
                    logging.error(f"[Канал {channel['name']}] Ошибка при отправке ключа шифрования")
            except Exception as e:
                logging.error(f"[Канал {channel['name']}] Ошибка при отправке ключа: {e}")
            finally:
                writer.close()
                await writer.wait_closed()

    async def send_segment(self, segment_number, total_segments, segment):
        retries = 0
        success = False
        while retries < self.retransmission_limit and not success:
            channel = self.select_best_channel()
            try:
                start_time = time.time()
                reader, writer = await asyncio.open_connection(channel['host'], channel['port'])
                checksum = hashlib.sha256(segment).digest()
                header = struct.pack('!I I 32s', self.session_id, segment_number, checksum)
                data_length = struct.pack('!I', len(segment))
                writer.write(header + data_length + segment)
                await writer.drain()
                ack = await reader.read(4)
                end_time = time.time()
                latency = end_time - start_time
                bandwidth = len(segment) / latency
                self.update_channel_state(channel['name'], latency, bandwidth)
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
                writer.close()
                await writer.wait_closed()

        if not success:
            logging.error(f"Не удалось отправить сегмент {segment_number + 1} после {self.retransmission_limit} попыток")

    async def send_fin_signal(self, total_segments):
        # Отправляем сигнал завершения передачи
        for channel in self.channels:
            try:
                reader, writer = await asyncio.open_connection(channel['host'], channel['port'])
                header = struct.pack('!I 4s', self.session_id, b'FIN')
                data_length = struct.pack('!I', 0)
                writer.write(header + data_length)
                await writer.drain()
                ack = await reader.read(4)
                if ack == b'ACK':
                    logging.info(f"[Канал {channel['name']}] Сигнал завершения передачи отправлен успешно")
                else:
                    logging.error(f"[Канал {channel['name']}] Ошибка при отправке сигнала завершения передачи")
            except Exception as e:
                logging.error(f"[Канал {channel['name']}] Ошибка: {e}")
            finally:
                writer.close()
                await writer.wait_closed()

    def update_channel_state(self, channel_name, latency, bandwidth):
        # Обновляем информацию о задержке и пропускной способности канала
        self.channel_states[channel_name]['latency'] = latency
        self.channel_states[channel_name]['bandwidth'] = bandwidth

    def select_best_channel(self):
        # Выбираем канал на основе комплексного алгоритма адаптации
        # Учитываем и задержку, и пропускную способность
        def channel_score(ch):
            latency = self.channel_states[ch['name']]['latency'] or float('inf')
            bandwidth = self.channel_states[ch['name']]['bandwidth'] or 0.0
            # Чем ниже латентность и выше пропускная способность, тем лучше
            return latency / (bandwidth + 1e-6)

        sorted_channels = sorted(self.channels, key=channel_score)
        return sorted_channels[0]

async def main():
    channels = [
        {'name': 'Channel1', 'host': '127.0.0.1', 'port': 8888},
        {'name': 'Channel2', 'host': '127.0.0.1', 'port': 8889},
    ]
    client = AggregatedClient(('127.0.0.1', 9000), channels)
    data = ('Данные для передачи ' * 1000).encode('utf-8')
    await client.send_data(data)

if __name__ == '__main__':
    asyncio.run(main())