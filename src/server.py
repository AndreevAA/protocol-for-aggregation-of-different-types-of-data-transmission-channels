# server.py
import asyncio
import hashlib
import struct
import logging
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import time

logging.basicConfig(level=logging.INFO)

class AggregatedServer:
    def __init__(self, channels):
        self.channels = channels
        self.session_data = {}
        self.locks = {}
        self.retransmission_limit = 3

    async def start_servers(self):
        servers = []
        for channel in self.channels:
            server = await asyncio.start_server(
                self.handle_client,
                channel['host'],
                channel['port']
            )
            servers.append(server)
            logging.info(f"Сервер запущен на {channel['host']}:{channel['port']} ({channel['name']})")
        await asyncio.gather(*(server.serve_forever() for server in servers))

    async def handle_client(self, reader, writer):
        session_start_time = time.time()

        try:
            while True:
                # Читаем заголовок
                header = await reader.readexactly(4 + 4)
                session_id, code = struct.unpack('!I 4s', header)
                code = str(code.decode('utf-8')).replace("\x00", "")

                if code == 'KEY':
                    # Обработка ключа шифрования
                    data_length_bytes = await reader.readexactly(4)
                    data_length = struct.unpack('!I', data_length_bytes)[0]
                    key_iv = await reader.readexactly(data_length)
                    key, iv = key_iv[:16], key_iv[16:]
                    self.store_encryption_key(session_id, key, iv)
                    writer.write(b'ACK')
                    await writer.drain()
                    logging.info(f"[Сессия {session_id}] Ключ шифрования получен")
                elif code == 'FIN':
                    # Обработка сигнала завершения передачи
                    writer.write(b'ACK')
                    await writer.drain()
                    await self.finalize_session(session_id)
                    logging.info(f"[Сессия {session_id}] Передача завершена")
                    break
                else:
                    # Обработка сегмента данных
                    segment_number = ord(code)
                    checksum = await reader.readexactly(32)
                    data_length_bytes = await reader.readexactly(4)
                    data_length = struct.unpack('!I', data_length_bytes)[0]
                    data = await reader.readexactly(data_length)
                    if hashlib.sha256(data).digest() == checksum:
                        writer.write(b'ACK')
                        await writer.drain()
                        await self.store_segment(session_id, segment_number, data)
                        logging.info(f"[Сессия {session_id}] Получен сегмент {segment_number}")
                    else:
                        writer.write(b'NACK')
                        await writer.drain()
                        logging.warning(f"[Сессия {session_id}] Ошибка контрольной суммы в сегменте {segment_number}")
        except asyncio.IncompleteReadError:
            pass  # Клиент закрыл соединение
        except Exception as e:
            logging.error(f"Ошибка при обработке клиента: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

        session_end_time = time.time()
        logging.info(
            f"[Сессия {session_id}] Обработка клиента завершена. Время сессии: {session_end_time - session_start_time:.2f} сек")

    def store_encryption_key(self, session_id, key, iv):
        if session_id not in self.session_data:
            self.session_data[session_id] = {'segments': {}, 'key': key, 'iv': iv, 'total_segments': None}
            self.locks[session_id] = asyncio.Lock()
        else:
            self.session_data[session_id]['key'] = key
            self.session_data[session_id]['iv'] = iv

    async def store_segment(self, session_id, segment_number, data):
        async with self.locks[session_id]:
            self.session_data[session_id]['segments'][segment_number] = data

    async def finalize_session(self, session_id):
        async with self.locks[session_id]:
            segments_data = self.session_data[session_id]['segments']
            key = self.session_data[session_id]['key']
            iv = self.session_data[session_id]['iv']

            # Собираем все сегменты в правильном порядке
            total_segments = len(segments_data)
            full_data_encrypted = b''.join(segments_data[i] for i in range(total_segments))

            # Расшифровываем данные
            cipher = AES.new(key, AES.MODE_CBC, iv)
            try:
                full_data = unpad(cipher.decrypt(full_data_encrypted), AES.block_size)
                logging.info(f"[Сессия {session_id}] Все данные успешно получены и расшифрованы. Длина: {len(full_data)} байт")
                # Обработка полученных данных
                # Например, сохраняем в файл
                with open(f'session_{session_id}.dat', 'wb') as f:
                    f.write(full_data)
            except ValueError as e:
                logging.error(f"[Сессия {session_id}] Ошибка при расшифровке данных: {e}")

            # Очищаем данные сессии
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