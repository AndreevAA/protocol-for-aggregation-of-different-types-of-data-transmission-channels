# load_test.py
import asyncio
import time
import random
import csv
from client import *

async def run_client(data_size, server_address, channels, stats):
    try:
        client = AggregatedClient(server_address, channels)
        data = b'x' * data_size  # Создаем данные заданного размера
        start_time = time.time()
        await client.send_data(data)
        end_time = time.time()
        elapsed_time = end_time - start_time
        stats.append({
            'data_size': data_size,
            'elapsed_time': elapsed_time,
            'status': 'success'
        })
    except Exception as e:
        stats.append({
            'data_size': data_size,
            'elapsed_time': None,
            'status': f'error: {e}'
        })

async def main():
    server_address = ('127.0.0.1', 8888)
    channels = [
        {'name': 'Channel1', 'host': '127.0.0.1', 'port': 8888},
        {'name': 'Channel2', 'host': '127.0.0.1', 'port': 8889},
    ]
    stats = []
    tasks = []
    num_clients = 50  # Количество параллельных клиентов
    data_size = 2048  # Размер данных, отправляемых каждым клиентом (в байтах)

    for _ in range(num_clients):
        task = asyncio.create_task(run_client(data_size, server_address, channels, stats))
        tasks.append(task)
        await asyncio.sleep(random.uniform(0, 0.05))  # Случайная задержка между запусками клиентов

    await asyncio.gather(*tasks)

    # Сохраняем статистику в CSV-файл
    with open('stats.csv', 'w', newline='') as csvfile:
        fieldnames = ['data_size', 'elapsed_time', 'status']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for stat in stats:
            writer.writerow(stat)

if __name__ == '__main__':
    asyncio.run(main())