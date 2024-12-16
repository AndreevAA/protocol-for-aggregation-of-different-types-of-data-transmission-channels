# server.py
import asyncio
import hashlib
import struct
import logging
from Crypto.Cipher import AES  # Импорт класса для шифрования AES
from Crypto.Util.Padding import unpad  # Импорт функции для удаления дополнений
import time

# Настройка базового логирования на уровне INFO
logging.basicConfig(level=logging.INFO)

class AggregatedServer:
    def __init__(self, channels):
        self.channels = channels  # Список каналов для запуска серверов
        self.session_data = {}  # Хранение данных сессий
        self.locks = {}  # Хранение блокировок для сессий
        self.retransmission_limit = 3  # Лимит на количество повторных передач

    async def start_servers(self):
        servers = []  # Список для хранения созданных серверов
        for channel in self.channels:
            # Запуск сервера для каждого канала
            server = await asyncio.start_server(
                self.handle_client,  # Функция для обработки клиентов
                channel['host'],  # Хост сервера
                channel['port']   # Порт сервера
            )
            servers.append(server)  # Добавление сервера в список
            logging.info(f"Сервер запущен на {channel['host']}:{channel['port']} ({channel['name']})")
        # Запуск всех серверов и ожидание их работы
        await asyncio.gather(*(server.serve_forever() for server in servers))

    async def handle_client(self, reader, writer):
        session_start_time = time.time()  # Время начала сессии

        try:
            while True:
                # Чтение заголовка сообщения
                header = await reader.readexactly(4 + 4)
                session_id, code = struct.unpack('!I 4s', header)  # Распаковка заголовка
                code = str(code.decode('utf-8')).replace("\x00", "")  # Очистка кода

                if code == 'KEY':
                    # Обработка ключа шифрования
                    data_length_bytes = await reader.readexactly(4)
                    data_length = struct.unpack('!I', data_length_bytes)[0]
                    key_iv = await reader.readexactly(data_length)  # Чтение ключа и IV
                    key, iv = key_iv[:16], key_iv[16:]  # Разделение на ключ и IV
                    self.store_encryption_key(session_id, key, iv)  # Сохранение ключа
                    writer.write(b'ACK')  # Подтверждение получения ключа
                    await writer.drain()  # Ожидание завершения записи
                    logging.info(f"[Сессия {session_id}] Ключ шифрования получен")
                elif code == 'FIN':
                    # Обработка сигнала о завершении передачи
                    writer.write(b'ACK')  # Подтверждение окончания передачи
                    await writer.drain()  # Ожидание завершения записи
                    await self.finalize_session(session_id)  # Завершение сессии
                    logging.info(f"[Сессия {session_id}] Передача завершена")
                    break  # Выход из цикла
                else:
                    # Обработка сегмента данных
                    segment_number = ord(code)  # Получение номера сегмента
                    checksum = await reader.readexactly(32)  # Чтение контрольной суммы
                    data_length_bytes = await reader.readexactly(4)  # Чтение длины данных
                    data_length = struct.unpack('!I', data_length_bytes)[0]
                    data = await reader.readexactly(data_length)  # Чтение самого сегмента данных
                    if hashlib.sha256(data).digest() == checksum:  # Проверка контрольной суммы
                        writer.write(b'ACK')  # Подтверждение получения
                        await writer.drain()  # Ожидание завершения записи
                        await self.store_segment(session_id, segment_number, data)  # Сохранение сегмента
                        logging.info(f"[Сессия {session_id}] Получен сегмент {segment_number}")
                    else:
                        writer.write(b'NACK')  # Отклонение сегмента
                        await writer.drain()  # Ожидание завершения записи
                        logging.warning(f"[Сессия {session_id}] Ошибка контрольной суммы в сегменте {segment_number}")
        except asyncio.IncompleteReadError:
            pass  # Клиент закрыл соединение
        except Exception as e:
            logging.error(f"Ошибка при обработке клиента: {e}")  # Логирование ошибок
        finally:
            writer.close()  # Закрытие соединения
            await writer.wait_closed()  # Ожидание закрытия

        session_end_time = time.time()  # Время окончания сессии
        logging.info(
            f"[Сессия {session_id}] Обработка клиента завершена. Время сессии: {session_end_time - session_start_time:.2f} сек")

    def store_encryption_key(self, session_id, key, iv):
        if session_id not in self.session_data:  # Если сессия новая
            self.session_data[session_id] = {'segments': {}, 'key': key, 'iv': iv, 'total_segments': None}  # Инициализация данных сессии
            self.locks[session_id] = asyncio.Lock()  # Инициализация блокировки
        else:
            # Обновление ключа и IV для существующей сессии
            self.session_data[session_id]['key'] = key
            self.session_data[session_id]['iv'] = iv

    async def store_segment(self, session_id, segment_number, data):
        async with self.locks[session_id]:  # Захват блокировки для записи
            self.session_data[session_id]['segments'][segment_number] = data  # Сохранение сегмента данных

    async def finalize_session(self, session_id):
        async with self.locks[session_id]:  # Захват блокировки для завершения
            segments_data = self.session_data[session_id]['segments']  # Получение данных сегментов
            key = self.session_data[session_id]['key']  # Получение ключа
            iv = self.session_data[session_id]['iv']  # Получение IV

            # Собираем все сегменты в правильном порядке
            total_segments = len(segments_data)  # Общее количество сегментов
            full_data_encrypted = b''.join(segments_data[i] for i in range(total_segments))  # Сборка сегментов в одно зашифрованное сообщение

            # Расшифровка данных
            cipher = AES.new(key, AES.MODE_CBC, iv)  # Инициализация шифра
            try:
                full_data = unpad(cipher.decrypt(full_data_encrypted), AES.block_size)  # Расшифровка и удаление дополнений
                logging.info(f"[Сессия {session_id}] Все данные успешно получены и расшифрованы. Длина: {len(full_data)} байт")
                # Обработка полученных данных (например, сохранение в файл)
                with open(f'session_{session_id}.dat', 'wb') as f:
                    f.write(full_data)  # Запись данных в файл
            except ValueError as e:
                logging.error(f"[Сессия {session_id}] Ошибка при расшифровке данных: {e}")  # Логирование ошибок расшифровки

            # Очищаем данные сессии после завершения
            del self.session_data[session_id]
            del self.locks[session_id]

async def main():
    channels = [
        {'name': 'Channel1', 'host': '127.0.0.1', 'port': 8888},
        {'name': 'Channel2', 'host': '127.0.0.1', 'port': 8889},
    ]
    server = AggregatedServer(channels)
    await server.start_servers()

if __name__ == '__main__':
    asyncio.run(main())