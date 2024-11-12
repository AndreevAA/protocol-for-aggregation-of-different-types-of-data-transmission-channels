import asyncio
import socket
import ssl
import threading
from fastapi import FastAPI
import uvicorn
from typing import Dict, List
import logging
import time

# Асинхронный подход для работы с сокетами и API
app = FastAPI()

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataHandler:
    def __init__(self):
        self.data_buffers: Dict[str, List[bytes]] = {}
        self.lock = threading.Lock()

    def add_data(self, client_id: str, data: bytes):
        with self.lock:
            if client_id not in self.data_buffers:
                self.data_buffers[client_id] = []
            self.data_buffers[client_id].append(data)
            logger.info(f"Data added for client {client_id}: {data}")

    def get_data(self, client_id: str):
        with self.lock:
            return self.data_buffers.get(client_id, [])


class ClientWorker:
    def __init__(self, client_socket, address, data_handler: DataHandler):
        self.client_socket = client_socket
        self.address = address
        self.data_handler = data_handler
        self.client_id = f"{address[0]}:{address[1]}"
        self.buffer_size = 1024

    def run(self):
        logger.info(f"Client connected: {self.client_id}")
        try:
            while True:
                data = self.client_socket.recv(self.buffer_size)
                if not data:
                    break
                self.data_handler.add_data(self.client_id, data)
        finally:
            self.client_socket.close()
            logger.info(f"Client disconnected: {self.client_id}")


async def server_task(data_handler: DataHandler):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 8080))
    server_socket.listen(5)
    server_socket.setblocking(False)

    while True:
        client_socket, address = await asyncio.get_running_loop().sock_accept(server_socket)
        worker = ClientWorker(client_socket, address, data_handler)
        thread = threading.Thread(target=worker.run)
        thread.start()


@app.get("/data/{client_id}")
async def get_client_data(client_id: str):
    return data_handler.get_data(client_id)


# Запускаем сервер
data_handler = DataHandler()
loop = asyncio.get_event_loop()
loop.create_task(server_task(data_handler))

# Запускаем FastAPI
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)