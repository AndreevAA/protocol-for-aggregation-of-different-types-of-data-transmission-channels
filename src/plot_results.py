# plot_results.py
import csv
import matplotlib.pyplot as plt

def read_stats(filename):
    data_sizes = []
    elapsed_times = []
    statuses = []
    with open(filename, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            data_sizes.append(int(row['data_size']))
            elapsed_time = row['elapsed_time']
            if elapsed_time:
                elapsed_times.append(float(elapsed_time))
            else:
                elapsed_times.append(None)
            statuses.append(row['status'])
    return data_sizes, elapsed_times, statuses

def plot_elapsed_times(elapsed_times):
    successful_times = [t for t in elapsed_times if t is not None]
    plt.figure(figsize=(10, 6))
    plt.hist(successful_times, bins=20, edgecolor='k')
    plt.xlabel('Время передачи (секунды)')
    plt.ylabel('Количество запросов')
    plt.title('Распределение времени передачи')
    plt.grid(True)
    plt.savefig('Распределение времени передачи.png')
    # plt.show()

def main():
    data_sizes, elapsed_times, statuses = read_stats('stats.csv')
    plot_elapsed_times(elapsed_times)

if __name__ == '__main__':
    main()