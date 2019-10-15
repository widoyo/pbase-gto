import time


def example(seconds):
    print('Starting Task')
    for i in range(seconds):
        print(i)
        time.sleep(1)
    print('Task completed')
